"""Local GLB export for generated meshes (Meshy export equivalent, local + free).

Meshy's pipeline is generate -> remesh to a budget -> PBR texture ->
rig -> export (GLB/FBX/OBJ/USDZ/STL/BLEND/3MF). SlushAI had no export
step at all: a generation produced an OBJ and nothing else. This
module is the export step for the one format that matters first:
GLB (glTF 2.0 binary) -- the format every web viewer, Blender, and
three.js loads directly.

Stdlib only, same as remesh.py and mesh_stats.py, so it is importable
without the Flask app and needs nothing installed into the app venv
(which has no numpy or trimesh).

What is written: a single glTF 2.0 asset with one scene, one node,
one mesh, one primitive -- POSITION + NORMAL attributes and an index
buffer, plus a plain PBR material (light grey, metal 0, roughness
0.9). Positions are float32, indices are uint16 when the vertex
count allows it (<= 65535) and uint32 above that -- TripoSR-scale
meshes (~137k-151k verts) need the wide form. Normals are computed
here (area-weighted per-vertex accumulation): the native backend
emits no normals, and a GLB without them renders flat black in most
viewers, so shipping them is the difference between a file that
opens and a file that looks right.

Honest limits, measured in tests/test_glb_export.py (this VM, shared):
- The export is geometry only: no textures, no UVs, no rigging, no
  PBR maps. Those are the next Meshy-ordered steps (PBR, then
  rigging, then text-to-3D) -- this step is the container they land in.
- Speed is pure-Python packing: the native mesh (4,225 verts /
  4,620 faces) exports in well under a second; TripoSR scale
  (~150k faces) is a few seconds. An export runs once per
  generation, async, after the mesh exists -- that is acceptable.
- Polygon faces are fan-triangulated, the same as remesh.decimate.
"""

import json
import struct
import time

from src.ai3d.utils.mesh_stats import count_obj_vertices_triangles
from src.ai3d.utils.remesh import read_obj

# glTF 2.0 binary container constants.
GLB_MAGIC = 0x46546C67  # 'glTF'
GLB_VERSION = 2
CHUNK_TYPE_JSON = 0x4E4F534A  # 'JSON'
CHUNK_TYPE_BIN = 0x004E4942  # 'BIN\0'

# glTF component types.
COMPONENT_FLOAT = 5126
COMPONENT_UNSIGNED_SHORT = 5123
COMPONENT_UNSIGNED_INT = 5125

# glTF buffer target types.
TARGET_ARRAY_BUFFER = 34962
TARGET_ELEMENT_ARRAY_BUFFER = 34963

# Above this vertex count an index no longer fits in 16 bits.
UINT16_MAX_VERTICES = 65535


class GlbExportError(ValueError):
    """Raised when a mesh cannot be exported (empty, degenerate, bad args)."""


# ---------------------------------------------------------------- vector helpers

def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _triangulate(faces):
    """Fan-triangulate polygon faces, dropping degenerate triangles."""
    tris = []
    for f in faces:
        for k in range(1, len(f) - 1):
            t = (f[0], f[k], f[k + 1])
            if len(set(t)) == 3:
                tris.append(t)
    return tris


def _compute_normals(vertices, tris):
    """Area-weighted smooth vertex normals.

    Each face contributes its (unnormalised) cross product to its
    three vertices, so larger faces weigh more; each vertex normal
    is then normalised. A vertex with no incident face (isolated,
    should not happen in a generated mesh) gets +Y so the accessor
    is never a zero vector.
    """
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


def _pad4(data, pad_byte=b'\x00'):
    """Pad bytes to a multiple of 4 with the given byte."""
    rem = len(data) % 4
    if rem:
        data += pad_byte * (4 - rem)
    return data


# ---------------------------------------------------------------- GLB writer

def write_glb(path, vertices, faces):
    """Write vertices/faces as a glTF 2.0 binary (.glb) file.

    vertices: list of (x, y, z) float tuples; faces: list of int
    tuples (polygons are fan-triangulated). Returns a dict with the
    vertex/triangle counts, the index component type used, the total
    file size in bytes, and elapsed seconds. Raises GlbExportError
    for an empty or degenerate mesh.
    """
    started = time.time()
    tris = _triangulate(faces)
    if not vertices or not tris:
        raise GlbExportError("Mesh has no triangles to export")
    n_verts = len(vertices)
    n_tris = len(tris)

    normals = _compute_normals(vertices, tris)

    pos_flat = [c for v in vertices for c in v]
    norm_flat = [c for n in normals for c in n]
    idx_flat = [i for t in tris for i in t]
    index_type = (COMPONENT_UNSIGNED_INT if n_verts > UINT16_MAX_VERTICES
                  else COMPONENT_UNSIGNED_SHORT)
    index_fmt = 'I' if index_type == COMPONENT_UNSIGNED_INT else 'H'

    pos_bytes = _pad4(struct.pack('<%df' % len(pos_flat), *pos_flat))
    norm_bytes = _pad4(struct.pack('<%df' % len(norm_flat), *norm_flat))
    idx_bytes = _pad4(struct.pack('<%d%s' % (len(idx_flat), index_fmt),
                                  *idx_flat))

    # Binary chunk sections are laid out back to back, each 4-byte
    # aligned (positions and normals already are: 12 bytes/vertex).
    pos_offset = 0
    norm_offset = len(pos_bytes)
    idx_offset = norm_offset + len(norm_bytes)
    bin_data = pos_bytes + norm_bytes + idx_bytes

    mins = [min(v[i] for v in vertices) for i in range(3)]
    maxs = [max(v[i] for v in vertices) for i in range(3)]

    gltf = {
        "asset": {"version": "2.0", "generator": "SlushAI glb export"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": "model"}],
        "meshes": [{
            "name": "model",
            "primitives": [{
                "attributes": {"POSITION": 0, "NORMAL": 1},
                "indices": 2,
                "material": 0,
            }],
        }],
        "materials": [{
            "name": "default",
            "pbrMetallicRoughness": {
                "baseColorFactor": [0.8, 0.8, 0.8, 1.0],
                "metallicFactor": 0.0,
                "roughnessFactor": 0.9,
            },
        }],
        "buffers": [{"byteLength": len(bin_data)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": pos_offset,
             "byteLength": len(pos_bytes), "target": TARGET_ARRAY_BUFFER},
            {"buffer": 0, "byteOffset": norm_offset,
             "byteLength": len(norm_bytes), "target": TARGET_ARRAY_BUFFER},
            {"buffer": 0, "byteOffset": idx_offset,
             "byteLength": len(idx_bytes),
             "target": TARGET_ELEMENT_ARRAY_BUFFER},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": COMPONENT_FLOAT,
             "count": n_verts, "type": "VEC3", "min": mins, "max": maxs},
            {"bufferView": 1, "componentType": COMPONENT_FLOAT,
             "count": n_verts, "type": "VEC3"},
            {"bufferView": 2, "componentType": index_type,
             "count": len(idx_flat), "type": "SCALAR"},
        ],
    }
    json_bytes = _pad4(json.dumps(gltf, separators=(',', ':')).encode('utf-8'),
                       pad_byte=b' ')

    total = 12 + 8 + len(json_bytes) + 8 + len(bin_data)
    with open(path, 'wb') as f:
        f.write(struct.pack('<III', GLB_MAGIC, GLB_VERSION, total))
        f.write(struct.pack('<II', len(json_bytes), CHUNK_TYPE_JSON))
        f.write(json_bytes)
        f.write(struct.pack('<II', len(bin_data), CHUNK_TYPE_BIN))
        f.write(bin_data)

    return {
        'output_vertices': n_verts,
        'output_faces': n_tris,
        'index_component_type': index_type,
        'glb_bytes': total,
        'output_path': path,
        'seconds': round(time.time() - started, 3),
    }


# ---------------------------------------------------------------- high-level entry

def export_glb(input_path, output_path):
    """Export the OBJ at input_path to a .glb at output_path.

    Returns a dict with input/output vertex and face counts (faces
    counted as triangles, Meshy-style), the index component type,
    the output path, the file size in bytes, and elapsed seconds.
    The reported counts are verified from disk: the written GLB is
    re-read (header + JSON chunk) and its accessor counts must
    match the input mesh, or the export fails. Raises GlbExportError
    for a missing file, an empty/degenerate input mesh, or a failed
    verification.
    """
    started = time.time()
    try:
        vertices, faces = read_obj(input_path)
    except (OSError, ValueError) as e:
        raise GlbExportError("Cannot read %s: %s" % (input_path, e))
    if not vertices or not faces:
        raise GlbExportError("No mesh found in %s" % input_path)
    # count_obj_vertices_triangles returns (vertices, triangles);
    # the budget/count that matters here is the triangle count.
    _, in_faces = count_obj_vertices_triangles(input_path)
    if in_faces == 0:
        raise GlbExportError("Mesh in %s has no faces" % input_path)

    result = write_glb(output_path, vertices, faces)

    # Verify from disk, so the reported counts are the file's counts.
    summary = read_glb_summary(output_path)
    if summary['vertices'] != len(vertices):
        raise GlbExportError(
            ("GLB verification failed for %s: %d vertices in file, "
             "%d in source") % (output_path, summary['vertices'],
                               len(vertices)))
    if summary['triangles'] != in_faces:
        raise GlbExportError(
            ("GLB verification failed for %s: %d triangles in file, "
             "%d in source") % (output_path, summary['triangles'],
                               in_faces))
    result['input_vertices'] = len(vertices)
    result['input_faces'] = in_faces
    result['seconds'] = round(time.time() - started, 3)
    return result


def read_glb_summary(path):
    """Read back a .glb header + JSON chunk without loading the mesh.

    Returns {'version', 'vertices', 'triangles', 'index_component_type',
    'has_normals', 'total_bytes'}. Raises GlbExportError for a file
    that is not a glTF 2.0 binary.
    """
    try:
        with open(path, 'rb') as f:
            data = f.read()
    except OSError as e:
        raise GlbExportError("Cannot read %s: %s" % (path, e))
    if len(data) < 20 or data[:4] != b'glTF':
        raise GlbExportError("%s is not a glTF binary file" % path)
    magic, version, total = struct.unpack('<III', data[:12])
    if version != 2 or total != len(data):
        raise GlbExportError(
            "%s: bad GLB header (version %d, declared %d bytes, "
            "actual %d)" % (path, version, total, len(data)))
    json_len, json_type = struct.unpack('<II', data[12:20])
    if json_type != CHUNK_TYPE_JSON:
        raise GlbExportError("%s: first chunk is not JSON" % path)
    try:
        gltf = json.loads(data[20:20 + json_len].decode('utf-8'))
    except (ValueError, UnicodeDecodeError) as e:
        raise GlbExportError("%s: bad JSON chunk: %s" % (path, e))
    accessors = gltf.get('accessors', [])
    meshes = gltf.get('meshes', [])
    if len(accessors) < 3 or not meshes:
        raise GlbExportError("%s: missing mesh accessors" % path)
    prim = meshes[0]['primitives'][0]
    attrs = prim.get('attributes', {})
    pos = accessors[attrs.get('POSITION', 0)]
    idx = accessors[prim['indices']]
    return {
        'version': version,
        'vertices': pos['count'],
        'triangles': idx['count'] // 3,
        'index_component_type': idx['componentType'],
        'has_normals': 'NORMAL' in attrs,
        'total_bytes': total,
    }


# ---------------------------------------------------------------- form flag + task wiring

_EXPORT_TRUE = {'1', 'true', 'yes', 'on'}
_EXPORT_FALSE = {'0', 'false', 'no', 'off', ''}


def parse_export_flag(value):
    """Parse the export_glb form flag.

    Accepts '1'/'true'/'yes'/'on' (any case) as True and
    '0'/'false'/'no'/'off'/''/None as False. Raises ValueError for
    anything else, so a typo'd value fails fast at the route
    instead of silently generating without a GLB.
    """
    if value is None:
        return False
    text = str(value).strip().lower()
    if text in _EXPORT_TRUE:
        return True
    if text in _EXPORT_FALSE:
        return False
    raise ValueError(
        "export_glb must be true or false, got %r" % (value,))


def export_glbs_for_generation(found_path, remeshed_path, export_flag,
                               log_warning):
    """Guarded GLB export for one generation task.

    found_path: the generated OBJ (pathlib Path). remeshed_path: the
    remeshed OBJ, or None when no remesh ran. export_flag: the
    parsed export_glb flag. log_warning: a callable taking a message
    string. Returns {'glb_path', 'glb_bytes', 'remeshed_glb_path',
    'remeshed_glb_bytes'} with Path objects (or None) and int sizes
    (or None). Never raises: an export failure logs a warning and
    leaves that entry None, so a generation never fails because its
    GLB export did -- the same guarantee the remesh step carries.
    When the flag is off nothing is written and every entry is None.
    """
    result = {'glb_path': None, 'glb_bytes': None,
              'remeshed_glb_path': None, 'remeshed_glb_bytes': None}
    if not export_flag:
        return result
    try:
        glb_path = found_path.with_name(found_path.stem + '.glb')
        info = export_glb(str(found_path), str(glb_path))
        result['glb_path'] = glb_path
        result['glb_bytes'] = info['glb_bytes']
    except Exception as e:
        log_warning("GLB export failed for %s: %s" % (found_path, e))
    if remeshed_path is not None:
        try:
            rglb_path = remeshed_path.with_name(remeshed_path.stem + '.glb')
            info = export_glb(str(remeshed_path), str(rglb_path))
            result['remeshed_glb_path'] = rglb_path
            result['remeshed_glb_bytes'] = info['glb_bytes']
        except Exception as e:
            log_warning("GLB export failed for %s: %s"
                        % (remeshed_path, e))
    return result
