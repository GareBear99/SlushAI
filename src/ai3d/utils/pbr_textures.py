"""Local PBR textures for generated meshes (Meshy PBR-texture equivalent, local + free).

Meshy's pipeline is generate -> remesh to a budget -> PBR texture ->
rig -> export. Remesh and GLB export are built; this module is step
(3): give a generated mesh real PBR maps so the GLB that ships is
not flat grey. The maps are procedural and deterministic -- the
native backend emits an untextured heightfield and there is no
external texture source (no network, no GPU, low-end CPU only) --
so colour and roughness are derived from the mesh itself: height
and slope, plus a seeded value-noise break-up.

What is built, per mesh:
- Planar UVs (the two largest bounding-box axes, normalised to
  [0, 1]) -- one UV per vertex, so the textured OBJ and the GLB
  share the same vertex order and the same UVs.
- A textured OBJ (<stem>_textured.obj) carrying vt lines, next to
  the original; the original is never modified.
- baseColor (albedo) PNG: a height-banded palette (dark soil low,
  moss mid, dry tan high, pale stone at the top) blended toward
  rock grey on steep slopes, broken up with two octaves of value
  noise. Default 256x256, stdlib-only PNG encoder (zlib).
- metallic-roughness PNG: glTF layout (R unused, G = roughness,
  B = metallic). Roughness 0.95 flat falling to 0.70 on steep
  slopes; metallic 0 everywhere -- these meshes are dielectric.
- GLB embedding (export_glb.py is NOT modified -- its md5 is
  pinned by the build contract): embed_pbr_in_glb post-processes
  a GLB the exporter wrote, appending the UVs and both PNGs to
  the BIN chunk and wiring TEXCOORD_0 + images + samplers +
  textures + material texture slots into the JSON chunk. The
  material factors are set to neutral (baseColorFactor white,
  metallic/roughness 1.0) so the maps show true.

Stdlib only, same as remesh.py / mesh_stats.py / export_glb.py,
so it is importable without the Flask app and needs nothing
installed into the app venv.

Honest limits, measured in tests/test_pbr_textures.py (this VM, shared):
- Procedural, not learned: the maps describe height and slope,
  they do not know what the mesh depicts. A TripoSR character
  gets terrain colours, not skin. A real texture model (or an
  image-conditioned one) is the later step; this is the container
  it lands in, and it makes the GLB visibly textured today.
- Planar UVs stretch on closed meshes (icosphere poles, TripoSR
  silhouettes) -- a proper unwrap is future work.
- No normal map yet: a tangent-space normal map needs tangents
  per vertex; the GLB ships smooth normals (from export_glb) and
  no normalTexture. That is the next PBR sub-step.
- No emissive, no occlusion map, no anisotropy -- base colour +
  metallic-roughness only, which is the glTF core PBR pair.
- Rasterisation cost is pure Python: the native mesh textures in
  well under a second at 256x256; TripoSR scale (~150k faces)
  extrapolates to a few seconds. A texture runs once per
  generation, async, so that is acceptable.
"""

import binascii
import json
import math
import os
import struct
import time
import zlib
from pathlib import Path

from src.ai3d.utils.mesh_stats import count_obj_vertices_triangles
from src.ai3d.utils.remesh import read_obj

# Texture resolution bounds (square). 256 is the default: enough
# detail for a 4k-vert heightfield, cheap to rasterise.
MIN_RESOLUTION = 64
MAX_RESOLUTION = 1024
DEFAULT_RESOLUTION = 256


class PbrError(ValueError):
    """Raised when a mesh cannot be textured (empty, degenerate, bad args)."""


# ---------------------------------------------------------------- vector helpers

def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _tri_normal(p0, p1, p2):
    """Unit face normal, or None for a degenerate (zero-area) triangle."""
    n = _cross(_sub(p1, p0), _sub(p2, p0))
    length = (n[0] ** 2 + n[1] ** 2 + n[2] ** 2) ** 0.5
    if length == 0.0:
        return None
    return (n[0] / length, n[1] / length, n[2] / length)


def _compute_normals(vertices, tris):
    """Area-weighted smooth vertex normals (same approach as
    export_glb: larger faces weigh more). Isolated vertices get +Y."""
    acc = [[0.0, 0.0, 0.0] for _ in vertices]
    for (a, b, c) in tris:
        n = _cross(_sub(vertices[b], vertices[a]),
                   _sub(vertices[c], vertices[a]))
        for i in (a, b, c):
            acc[i][0] += n[0]
            acc[i][1] += n[1]
            acc[i][2] += n[2]
    normals = []
    for (x, y, z) in acc:
        length = (x * x + y * y + z * z) ** 0.5
        if length == 0.0:
            normals.append((0.0, 1.0, 0.0))
        else:
            normals.append((x / length, y / length, z / length))
    return normals


def _triangulate(faces):
    """Fan-triangulate polygon faces, dropping degenerate triangles."""
    tris = []
    for f in faces:
        for k in range(1, len(f) - 1):
            t = (f[0], f[k], f[k + 1])
            if len(set(t)) == 3:
                tris.append(t)
    return tris


def _clamp01(x):
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


# ---------------------------------------------------------------- UVs + features

def compute_uvs(vertices, faces):
    """Planar UVs from the two largest bounding-box axes.

    The mesh is projected onto the plane spanned by its two
    longest axes and normalised to [0, 1] -- for the native
    heightfield (X/Z plane, Y up) that is the natural top-down
    map. Returns a list of (u, v) per vertex. A zero-extent axis
    maps to 0.0 everywhere on that coordinate.
    """
    if not vertices:
        raise PbrError("Cannot compute UVs for an empty mesh")
    mins = [min(v[i] for v in vertices) for i in range(3)]
    maxs = [max(v[i] for v in vertices) for i in range(3)]
    extents = [maxs[i] - mins[i] for i in range(3)]
    order = sorted(range(3), key=lambda i: extents[i], reverse=True)
    ax_u, ax_v = order[0], order[1]
    uvs = []
    for v in vertices:
        u = ((v[ax_u] - mins[ax_u]) / extents[ax_u]
             if extents[ax_u] > 0 else 0.0)
        w = ((v[ax_v] - mins[ax_v]) / extents[ax_v]
             if extents[ax_v] > 0 else 0.0)
        uvs.append((_clamp01(u), _clamp01(w)))
    return uvs


def compute_vertex_features(vertices, faces):
    """Per-vertex height and slope, both in [0, 1].

    Height is the normalised coordinate along the remaining axis
    (the one NOT used for the UV plane -- the mesh's "up"). Slope
    is 1 minus the normal's component along that axis: 0 for a
    flat-up face, 1 for a vertical wall. Returns (heights, slopes).
    """
    tris = _triangulate(faces)
    if not vertices or not tris:
        raise PbrError("Mesh has no triangles to texture")
    mins = [min(v[i] for v in vertices) for i in range(3)]
    maxs = [max(v[i] for v in vertices) for i in range(3)]
    extents = [maxs[i] - mins[i] for i in range(3)]
    order = sorted(range(3), key=lambda i: extents[i], reverse=True)
    ax_up = order[2]
    heights = []
    for v in vertices:
        h = ((v[ax_up] - mins[ax_up]) / extents[ax_up]
             if extents[ax_up] > 0 else 0.5)
        heights.append(_clamp01(h))
    normals = _compute_normals(vertices, tris)
    slopes = []
    for n in normals:
        slopes.append(_clamp01(1.0 - abs(n[ax_up])))
    return heights, slopes


# ---------------------------------------------------------------- value noise

def _lattice(ix, iy, seed):
    """Deterministic pseudo-random value in [0, 1) for a lattice point."""
    h = (ix * 374761393 + iy * 668265263 + seed * 974634211) & 0xFFFFFFFF
    h = (h ^ (h >> 13)) & 0xFFFFFFFF
    h = (h * 1274126177) & 0xFFFFFFFF
    h = (h ^ (h >> 16)) & 0xFFFFFFFF
    return h / 4294967296.0


def _noise2(u, v, seed):
    """Smooth 2D value noise in [0, 1]: bilinear interpolation of
    lattice values with a smoothstep falloff."""
    ix = math.floor(u)
    iy = math.floor(v)
    fx = u - ix
    fy = v - iy
    sx = fx * fx * (3.0 - 2.0 * fx)
    sy = fy * fy * (3.0 - 2.0 * fy)
    a = _lattice(ix, iy, seed)
    b = _lattice(ix + 1, iy, seed)
    c = _lattice(ix, iy + 1, seed)
    d = _lattice(ix + 1, iy + 1, seed)
    return (a + (b - a) * sx + (c - a) * sy
            + (a - b - c + d) * sx * sy)


def _detail_noise(u, v, seed):
    """Two octaves of value noise, in [0, 1]."""
    return (0.65 * _noise2(u * 6.0, v * 6.0, seed)
            + 0.35 * _noise2(u * 13.0, v * 13.0, seed + 7))


# ---------------------------------------------------------------- PNG encoder (stdlib only)

def encode_png_rgb(width, height, rows):
    """Encode rows of (r, g, b) int tuples as a minimal PNG (8-bit
    RGB, filter 0, zlib level 6). rows is a list of height rows,
    each a list of width (r, g, b) tuples. Returns the PNG bytes.
    """
    if width <= 0 or height <= 0:
        raise PbrError("PNG dimensions must be positive")
    if len(rows) != height:
        raise PbrError("PNG row count %d != height %d"
                       % (len(rows), height))
    raw = bytearray()
    for row in rows:
        if len(row) != width:
            raise PbrError("PNG row width %d != %d" % (len(row), width))
        raw.append(0)  # filter: none
        for (r, g, b) in row:
            raw.append(r & 0xFF)
            raw.append(g & 0xFF)
            raw.append(b & 0xFF)
    comp = zlib.compress(bytes(raw), 6)

    def chunk(ctype, data):
        out = struct.pack('>I', len(data)) + ctype + data
        out += struct.pack('>I', binascii.crc32(ctype + data) & 0xFFFFFFFF)
        return out

    ihdr = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', ihdr)
    png += chunk(b'IDAT', comp)
    png += chunk(b'IEND', b'')
    return png


# ---------------------------------------------------------------- palette

# Height-banded albedo palette (height -> (r, g, b)): dark soil low,
# moss mid, dry tan high, pale stone at the top.
_PALETTE = (
    (0.00, (58, 44, 30)),
    (0.30, (96, 104, 58)),
    (0.55, (150, 128, 80)),
    (0.80, (186, 176, 158)),
    (1.00, (214, 208, 196)),
)
_ROCK_GREY = (128, 124, 118)


def _palette_color(h, slope, u, v, seed):
    """Albedo colour for one texel: palette by height, blended to
    rock grey on steep slopes, broken up with value noise."""
    h = _clamp01(h)
    if h <= _PALETTE[0][0]:
        base = _PALETTE[0][1]
    elif h >= _PALETTE[-1][0]:
        base = _PALETTE[-1][1]
    else:
        base = _PALETTE[-1][1]
        for i in range(len(_PALETTE) - 1):
            h0, c0 = _PALETTE[i]
            h1, c1 = _PALETTE[i + 1]
            if h0 <= h <= h1:
                t = (h - h0) / (h1 - h0) if h1 > h0 else 0.0
                base = tuple(int(round(c0[k] + (c1[k] - c0[k]) * t))
                             for k in range(3))
                break
    rock = _clamp01((slope - 0.45) / 0.40)
    rgb = [int(round(base[k] + (_ROCK_GREY[k] - base[k]) * rock))
           for k in range(3)]
    bright = 0.88 + 0.24 * _detail_noise(u, v, seed)
    return tuple(max(0, min(255, int(round(c * bright)))) for c in rgb)


def _mr_color(slope):
    """Metallic-roughness texel (glTF layout: R unused, G =
    roughness, B = metallic). Roughness 0.95 flat -> 0.70 steep;
    metallic 0 -- dielectric meshes."""
    rough = 0.95 - 0.25 * _clamp01(slope)
    return (255, int(round(rough * 255)), 0)


# ---------------------------------------------------------------- rasterisation

def _rasterize_features(vertices, faces, uvs, heights, slopes, resolution):
    """Rasterise per-vertex height/slope into texture grids.

    Each triangle's UV footprint is scan-converted with barycentric
    interpolation; overlapping triangles average. Returns
    (height_grid, slope_grid, covered): flat lists of length
    resolution*resolution (row-major, v=0 at row 0), plus a
    covered-bool list. Uncovered texels are filled afterwards:
    one dilation pass from covered 4-neighbours, then any stragglers
    take the global mean of the covered texels.
    """
    res = resolution
    n = res * res
    h_sum = [0.0] * n
    s_sum = [0.0] * n
    count = [0] * n
    tris = _triangulate(faces)
    for (a, b, c) in tris:
        ua, va = uvs[a]
        ub, vb = uvs[b]
        uc, vc = uvs[c]
        min_u = max(0, int(min(ua, ub, uc) * res))
        max_u = min(res - 1, int(max(ua, ub, uc) * res))
        min_v = max(0, int(min(va, vb, vc) * res))
        max_v = min(res - 1, int(max(va, vb, vc) * res))
        denom = (vb - vc) * (ua - uc) + (uc - ub) * (va - vc)
        if abs(denom) < 1e-12:
            continue  # degenerate in UV space
        for py in range(min_v, max_v + 1):
            cy = (py + 0.5) / res
            for px in range(min_u, max_u + 1):
                cx = (px + 0.5) / res
                w0 = ((vb - vc) * (cx - uc) + (uc - ub) * (cy - vc)) / denom
                w1 = ((vc - va) * (cx - uc) + (ua - uc) * (cy - vc)) / denom
                w2 = 1.0 - w0 - w1
                if w0 < -1e-9 or w1 < -1e-9 or w2 < -1e-9:
                    continue
                idx = py * res + px
                h_sum[idx] += w0 * heights[a] + w1 * heights[b] + w2 * heights[c]
                s_sum[idx] += w0 * slopes[a] + w1 * slopes[b] + w2 * slopes[c]
                count[idx] += 1
    h_grid = [0.0] * n
    s_grid = [0.0] * n
    covered = [False] * n
    h_mean = 0.0
    s_mean = 0.0
    n_cov = 0
    for i in range(n):
        if count[i]:
            h_grid[i] = h_sum[i] / count[i]
            s_grid[i] = s_sum[i] / count[i]
            covered[i] = True
            h_mean += h_grid[i]
            s_mean += s_grid[i]
            n_cov += 1
    if n_cov == 0:
        raise PbrError("Mesh covers no texture area (degenerate UVs)")
    h_mean /= n_cov
    s_mean /= n_cov
    # One dilation pass, then the global mean for anything left.
    for py in range(res):
        for px in range(res):
            idx = py * res + px
            if covered[idx]:
                continue
            vals = []
            for (nx, ny) in ((px - 1, py), (px + 1, py),
                             (px, py - 1), (px, py + 1)):
                if 0 <= nx < res and 0 <= ny < res:
                    j = ny * res + nx
                    if covered[j]:
                        vals.append((h_grid[j], s_grid[j]))
            if vals:
                h_grid[idx] = sum(v[0] for v in vals) / len(vals)
                s_grid[idx] = sum(v[1] for v in vals) / len(vals)
                covered[idx] = True
    for i in range(n):
        if not covered[i]:
            h_grid[i] = h_mean
            s_grid[i] = s_mean
            covered[i] = True
    return h_grid, s_grid, covered


def make_basecolor_png(vertices, faces, uvs, resolution=DEFAULT_RESOLUTION,
                       seed=0):
    """Render the base-colour (albedo) map as PNG bytes."""
    if not (MIN_RESOLUTION <= resolution <= MAX_RESOLUTION):
        raise PbrError("resolution must be %d-%d, got %r"
                       % (MIN_RESOLUTION, MAX_RESOLUTION, resolution))
    heights, slopes = compute_vertex_features(vertices, faces)
    h_grid, s_grid, _ = _rasterize_features(
        vertices, faces, uvs, heights, slopes, resolution)
    rows = []
    for py in range(resolution):
        row = []
        for px in range(resolution):
            idx = py * resolution + px
            row.append(_palette_color(
                h_grid[idx], s_grid[idx],
                (px + 0.5) / resolution, (py + 0.5) / resolution, seed))
        rows.append(row)
    return encode_png_rgb(resolution, resolution, rows)


def make_metallic_roughness_png(vertices, faces, uvs,
                                resolution=DEFAULT_RESOLUTION, seed=0):
    """Render the metallic-roughness map as PNG bytes (R unused,
    G = roughness, B = metallic). Seed is accepted for a uniform
    call shape; the map has no noise term."""
    if not (MIN_RESOLUTION <= resolution <= MAX_RESOLUTION):
        raise PbrError("resolution must be %d-%d, got %r"
                       % (MIN_RESOLUTION, MAX_RESOLUTION, resolution))
    heights, slopes = compute_vertex_features(vertices, faces)
    h_grid, s_grid, _ = _rasterize_features(
        vertices, faces, uvs, heights, slopes, resolution)
    rows = []
    for py in range(resolution):
        row = []
        for px in range(resolution):
            idx = py * resolution + px
            row.append(_mr_color(s_grid[idx]))
        rows.append(row)
    return encode_png_rgb(resolution, resolution, rows)


# ---------------------------------------------------------------- textured OBJ

def write_textured_obj(input_path, output_path, uvs):
    """Write the OBJ at input_path with vt lines at output_path.

    One UV per vertex (same order as the vertices), faces written
    as 'f a/a b/b c/c'. Returns (vertex_count, uv_count,
    triangle_count) verified by re-reading the written file's line
    counts. Raises PbrError for a missing/empty input or a UV
    count that does not match the vertex count.
    """
    try:
        vertices, faces = read_obj(input_path)
    except OSError as e:
        raise PbrError("Cannot read %s: %s" % (input_path, e))
    if not vertices or not faces:
        raise PbrError("No mesh found in %s" % input_path)
    if len(uvs) != len(vertices):
        raise PbrError("UV count %d != vertex count %d for %s"
                       % (len(uvs), len(vertices), input_path))
    tris = _triangulate(faces)
    with open(output_path, 'w') as f:
        for (x, y, z) in vertices:
            f.write("v %r %r %r\n" % (x, y, z))
        for (u, v) in uvs:
            f.write("vt %r %r\n" % (u, v))
        for t in tris:
            f.write("f " + " ".join("%d/%d" % (i + 1, i + 1) for i in t)
                    + "\n")
    # Verify from disk: vt lines == vertices, faces triangulated.
    v_lines = vt_lines = f_lines = 0
    with open(output_path, 'r', errors='ignore') as f:
        for line in f:
            if line.startswith('v '):
                v_lines += 1
            elif line.startswith('vt '):
                vt_lines += 1
            elif line.startswith('f '):
                f_lines += 1
    if v_lines != len(vertices) or vt_lines != len(uvs):
        raise PbrError("Textured OBJ verification failed for %s: "
                       "%d v lines, %d vt lines" % (output_path,
                                                    v_lines, vt_lines))
    return len(vertices), len(uvs), f_lines


# ---------------------------------------------------------------- high-level entry

def generate_pbr_for_obj(input_path, output_path=None,
                         resolution=DEFAULT_RESOLUTION, seed=0):
    """Texture the OBJ at input_path with PBR maps.

    Writes <stem>_textured.obj (vt lines) plus
    <stem>_basecolor.png and <stem>_metallicroughness.png next to
    it (output_path overrides the textured OBJ path; the PNGs sit
    next to whatever that path is). Returns a dict with input
    vertex/face counts, the UV count, the three output paths, the
    PNG byte sizes, the resolution, and elapsed seconds. The
    reported counts are verified from disk. Raises PbrError for a
    missing/empty/degenerate input or an out-of-range resolution.
    The source OBJ is never modified.
    """
    started = time.time()
    if not (MIN_RESOLUTION <= resolution <= MAX_RESOLUTION):
        raise PbrError("resolution must be %d-%d, got %r"
                       % (MIN_RESOLUTION, MAX_RESOLUTION, resolution))
    try:
        vertices, faces = read_obj(input_path)
    except OSError as e:
        raise PbrError("Cannot read %s: %s" % (input_path, e))
    if not vertices or not faces:
        raise PbrError("No mesh found in %s" % input_path)
    _, in_faces = count_obj_vertices_triangles(input_path)
    if in_faces == 0:
        raise PbrError("Mesh in %s has no faces" % input_path)
    uvs = compute_uvs(vertices, faces)
    if output_path is None:
        stem = os.path.splitext(input_path)[0]
        output_path = stem + '_textured.obj'
    base = os.path.splitext(output_path)[0]
    basecolor_path = base + '_basecolor.png'
    mr_path = base + '_metallicroughness.png'
    out_v, out_uv, out_f = write_textured_obj(input_path, output_path, uvs)
    basecolor_png = make_basecolor_png(vertices, faces, uvs,
                                       resolution, seed)
    with open(basecolor_path, 'wb') as f:
        f.write(basecolor_png)
    mr_png = make_metallic_roughness_png(vertices, faces, uvs,
                                         resolution, seed)
    with open(mr_path, 'wb') as f:
        f.write(mr_png)
    return {
        'input_vertices': len(vertices),
        'input_faces': in_faces,
        'output_vertices': out_v,
        'output_faces': out_f,
        'uv_count': out_uv,
        'textured_path': output_path,
        'basecolor_path': basecolor_path,
        'basecolor_bytes': len(basecolor_png),
        'metallic_roughness_path': mr_path,
        'metallic_roughness_bytes': len(mr_png),
        'resolution': resolution,
        'seconds': round(time.time() - started, 3),
    }


def _pbr_for_one(obj_path, resolution, seed):
    """generate_pbr_for_obj plus the UV list (kept in-process for
    the GLB embed step; the public result dict carries counts,
    not the list)."""
    vertices, faces = read_obj(obj_path)
    uvs = compute_uvs(vertices, faces)
    info = generate_pbr_for_obj(obj_path, None, resolution, seed)
    return info, uvs


# ---------------------------------------------------------------- GLB embedding

GLB_MAGIC = 0x46546C67
GLB_VERSION = 2
CHUNK_TYPE_JSON = 0x4E4F534A
CHUNK_TYPE_BIN = 0x004E4942


def _pad4(data, pad_byte=b'\x00'):
    rem = len(data) % 4
    if rem:
        data += pad_byte * (4 - rem)
    return data


def _read_glb(path):
    """Parse a .glb header + JSON chunk + BIN bytes. Returns
    (gltf_dict, bin_bytes). Raises PbrError for a non-glTF file."""
    try:
        with open(path, 'rb') as f:
            data = f.read()
    except OSError as e:
        raise PbrError("Cannot read %s: %s" % (path, e))
    if len(data) < 20 or data[:4] != b'glTF':
        raise PbrError("%s is not a glTF binary file" % path)
    magic, version, total = struct.unpack('<III', data[:12])
    if version != 2 or total != len(data):
        raise PbrError("%s: bad GLB header (version %d, declared %d "
                       "bytes, actual %d)" % (path, version, total,
                                             len(data)))
    json_len, json_type = struct.unpack('<II', data[12:20])
    if json_type != CHUNK_TYPE_JSON:
        raise PbrError("%s: first chunk is not JSON" % path)
    try:
        gltf = json.loads(data[20:20 + json_len].decode('utf-8'))
    except (ValueError, UnicodeDecodeError) as e:
        raise PbrError("%s: bad JSON chunk: %s" % (path, e))
    bin_off = 20 + json_len
    if len(data) < bin_off + 8:
        raise PbrError("%s: missing BIN chunk" % path)
    bin_len, bin_type = struct.unpack('<II', data[bin_off:bin_off + 8])
    if bin_type != CHUNK_TYPE_BIN:
        raise PbrError("%s: second chunk is not BIN" % path)
    return gltf, data[bin_off + 8:bin_off + 8 + bin_len]


def embed_pbr_in_glb(glb_path, uvs, basecolor_png, mr_png,
                     output_path=None):
    """Embed PBR textures into a GLB written by export_glb.py.

    export_glb.py is not modified (its md5 is pinned): this
    post-processes its output. The UV float data and both PNGs are
    appended to the BIN chunk; the JSON chunk gains bufferViews +
    accessors for them, TEXCOORD_0 on the primitive, images +
    samplers + textures, and material texture slots (factors set
    neutral so the maps show true). The GLB's vertex count must
    match len(uvs) or the embed fails. Writes via a temp file +
    os.replace, so a failure never leaves a half-written GLB, and
    verifies the result from disk before returning. Returns a dict
    with the output path, the new file size, and elapsed seconds.
    Raises PbrError for a bad GLB, a UV count mismatch, or a
    failed verification.
    """
    started = time.time()
    if output_path is None:
        output_path = glb_path
    gltf, bin_data = _read_glb(glb_path)
    meshes = gltf.get('meshes', [])
    accessors = gltf.get('accessors', [])
    if not meshes or not accessors:
        raise PbrError("%s: no mesh accessors to texture" % glb_path)
    prim = meshes[0]['primitives'][0]
    attrs = prim.get('attributes', {})
    if 'POSITION' not in attrs:
        raise PbrError("%s: primitive has no POSITION" % glb_path)
    n_verts = accessors[attrs['POSITION']]['count']
    if len(uvs) != n_verts:
        raise PbrError("UV count %d != GLB vertex count %d for %s"
                       % (len(uvs), n_verts, glb_path))

    uv_flat = [c for uv in uvs for c in uv]
    uv_bytes = _pad4(struct.pack('<%df' % len(uv_flat), *uv_flat))
    bc_bytes = _pad4(bytes(basecolor_png))
    mr_bytes = _pad4(bytes(mr_png))
    uv_offset = len(bin_data)
    bc_offset = uv_offset + len(uv_bytes)
    mr_offset = bc_offset + len(bc_bytes)
    new_bin = bin_data + uv_bytes + bc_bytes + mr_bytes

    buffer_views = list(gltf.get('bufferViews', []))
    uv_bv = len(buffer_views)
    buffer_views.append({"buffer": 0, "byteOffset": uv_offset,
                         "byteLength": len(uv_bytes),
                         "target": 34962})
    bc_bv = len(buffer_views)
    buffer_views.append({"buffer": 0, "byteOffset": bc_offset,
                         "byteLength": len(bc_bytes)})
    mr_bv = len(buffer_views)
    buffer_views.append({"buffer": 0, "byteOffset": mr_offset,
                         "byteLength": len(mr_bytes)})
    gltf['bufferViews'] = buffer_views

    uv_acc = len(accessors)
    accessors.append({"bufferView": uv_bv, "componentType": 5126,
                      "count": len(uvs), "type": "VEC2",
                      "min": [0.0, 0.0], "max": [1.0, 1.0]})
    gltf['accessors'] = accessors

    images = list(gltf.get('images', []))
    images.append({"bufferView": bc_bv, "mimeType": "image/png",
                   "name": "baseColor"})
    images.append({"bufferView": mr_bv, "mimeType": "image/png",
                   "name": "metallicRoughness"})
    gltf['images'] = images
    samplers = list(gltf.get('samplers', []))
    samplers.append({"magFilter": 9729, "minFilter": 9987,
                     "wrapS": 10497, "wrapT": 10497})
    gltf['samplers'] = samplers
    textures = list(gltf.get('textures', []))
    textures.append({"sampler": 0, "source": 0})
    textures.append({"sampler": 0, "source": 1})
    gltf['textures'] = textures

    prim['attributes'] = dict(attrs)
    prim['attributes']['TEXCOORD_0'] = uv_acc
    materials = list(gltf.get('materials', []))
    if not materials:
        raise PbrError("%s: no material to texture" % glb_path)
    mat = dict(materials[0])
    pbr = dict(mat.get('pbrMetallicRoughness', {}))
    pbr['baseColorFactor'] = [1.0, 1.0, 1.0, 1.0]
    pbr['metallicFactor'] = 1.0
    pbr['roughnessFactor'] = 1.0
    pbr['baseColorTexture'] = {"index": 0}
    pbr['metallicRoughnessTexture'] = {"index": 1}
    mat['pbrMetallicRoughness'] = pbr
    materials[0] = mat
    gltf['materials'] = materials
    gltf['buffers'] = [{"byteLength": len(new_bin)}]

    json_bytes = _pad4(json.dumps(gltf, separators=(',', ':')).encode('utf-8'),
                       pad_byte=b' ')
    total = 12 + 8 + len(json_bytes) + 8 + len(new_bin)
    tmp_path = output_path + '.tmp-pbr'
    with open(tmp_path, 'wb') as f:
        f.write(struct.pack('<III', GLB_MAGIC, GLB_VERSION, total))
        f.write(struct.pack('<II', len(json_bytes), CHUNK_TYPE_JSON))
        f.write(json_bytes)
        f.write(struct.pack('<II', len(new_bin), CHUNK_TYPE_BIN))
        f.write(new_bin)
    os.replace(tmp_path, output_path)

    # Verify from disk: the embedded GLB must re-parse with the
    # UV accessor, both images, both textures, and both material
    # texture slots, at the right counts.
    gltf2, _ = _read_glb(output_path)
    prim2 = gltf2['meshes'][0]['primitives'][0]
    attrs2 = prim2.get('attributes', {})
    if 'TEXCOORD_0' not in attrs2:
        raise PbrError("GLB embed verification failed for %s: no "
                       "TEXCOORD_0" % output_path)
    if gltf2['accessors'][attrs2['TEXCOORD_0']]['count'] != len(uvs):
        raise PbrError("GLB embed verification failed for %s: UV "
                       "accessor count mismatch" % output_path)
    if len(gltf2.get('images', [])) != 2:
        raise PbrError("GLB embed verification failed for %s: "
                       "expected 2 images" % output_path)
    pbr2 = gltf2['materials'][0]['pbrMetallicRoughness']
    if ('baseColorTexture' not in pbr2
            or 'metallicRoughnessTexture' not in pbr2):
        raise PbrError("GLB embed verification failed for %s: "
                       "material texture slots missing" % output_path)
    return {
        'output_path': output_path,
        'glb_bytes': total,
        'uv_count': len(uvs),
        'seconds': round(time.time() - started, 3),
    }


# ---------------------------------------------------------------- form flag + task wiring

_PBR_TRUE = {'1', 'true', 'yes', 'on'}
_PBR_FALSE = {'0', 'false', 'no', 'off', ''}


def parse_pbr_flag(value):
    """Parse the pbr_textures form flag.

    Accepts '1'/'true'/'yes'/'on' (any case) as True and
    '0'/'false'/'no'/'off'/''/None as False. Raises ValueError for
    anything else, so a typo'd value fails fast at the route
    instead of silently generating without textures.
    """
    if value is None:
        return False
    text = str(value).strip().lower()
    if text in _PBR_TRUE:
        return True
    if text in _PBR_FALSE:
        return False
    raise ValueError(
        "pbr_textures must be true or false, got %r" % (value,))


def apply_pbr_for_generation(found_path, remeshed_path, glb_paths,
                             pbr_flag, log_warning,
                             resolution=DEFAULT_RESOLUTION, seed=0):
    """Guarded PBR texturing for one generation task.

    found_path: the generated OBJ (pathlib Path). remeshed_path:
    the remeshed OBJ, or None when no remesh ran. glb_paths: the
    dict export_glbs_for_generation returned (may hold None
    entries). pbr_flag: the parsed pbr_textures flag. log_warning:
    a callable taking a message string. Returns a dict with the
    textured OBJ + PNG paths and byte sizes (or None), the UV
    counts, and whether each GLB got its textures embedded. Never
    raises: a texturing failure logs a warning and leaves that
    entry None, so a generation never fails because its textures
    did -- the same guarantee the remesh and GLB steps carry.
    When the flag is off nothing is written and every entry is
    None/False.
    """
    result = {
        'textured_path': None, 'basecolor_path': None,
        'basecolor_bytes': None, 'metallic_roughness_path': None,
        'metallic_roughness_bytes': None, 'uv_count': None,
        'remeshed_textured_path': None,
        'remeshed_basecolor_path': None,
        'remeshed_basecolor_bytes': None,
        'remeshed_metallic_roughness_path': None,
        'remeshed_metallic_roughness_bytes': None,
        'remeshed_uv_count': None,
        'glb_pbr_embedded': False,
        'remeshed_glb_pbr_embedded': False,
    }
    if not pbr_flag:
        return result

    def _one(obj_path, glb_path, prefix):
        try:
            info, uvs = _pbr_for_one(str(obj_path), resolution, seed)
        except Exception as e:
            log_warning("PBR texturing failed for %s: %s" % (obj_path, e))
            return
        result[prefix + 'textured_path'] = Path(info['textured_path'])
        result[prefix + 'basecolor_path'] = Path(info['basecolor_path'])
        result[prefix + 'basecolor_bytes'] = info['basecolor_bytes']
        result[prefix + 'metallic_roughness_path'] = Path(
            info['metallic_roughness_path'])
        result[prefix + 'metallic_roughness_bytes'] = \
            info['metallic_roughness_bytes']
        result[prefix + 'uv_count'] = info['uv_count']
        if glb_path is not None:
            try:
                with open(info['basecolor_path'], 'rb') as f:
                    bc_png = f.read()
                with open(info['metallic_roughness_path'], 'rb') as f:
                    mr_png = f.read()
                embed_pbr_in_glb(str(glb_path), uvs, bc_png, mr_png)
                result[prefix + 'glb_pbr_embedded'] = True
            except Exception as e:
                log_warning("PBR GLB embed failed for %s: %s"
                            % (glb_path, e))

    _one(found_path, glb_paths.get('glb_path'), '')
    if remeshed_path is not None:
        _one(remeshed_path, glb_paths.get('remeshed_glb_path'), 'remeshed_')
    return result
