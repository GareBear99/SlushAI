"""Local remesh / decimation to a target face budget (Meshy Remesh equivalent, local + free).

Meshy's pipeline is generate -> remesh to a target budget
(target_polycount 100-300,000 faces, quad or triangle, faces counted
as triangles) -> PBR texture -> rig -> export. SlushAI had no remesh
step at all: the native backend emits whatever it emits (~4,225
verts, open heightfield) and TripoSR emits ~137k-151k verts, with no
way to ask for a budget in between. This module is step (1) of that
pipeline: take a generated OBJ and decimate it to a requested target
face count, triangle or quad output.

Stdlib only, same as mesh_stats.py, so it is importable without the
Flask app and needs nothing installed into the app venv (which has no
numpy, trimesh, or fast-simplification).

Algorithm: Garland-Heckbert quadric error metric (QEM) edge collapse
-- the standard decimation algorithm, implemented here in pure
Python. Each vertex carries a 4x4 quadric built from its incident
face planes; collapsing an edge to its error-minimising position is
priced by that quadric, and the cheapest edge goes first (heap with
lazy cost recomputation, so stale entries are re-priced, never
trusted). Two guards keep the mesh valid:

- Link condition: an edge (u, v) may collapse only when the vertices
  adjacent to both u and v number exactly the faces the edge belongs
  to. This is what stops a collapse from punching a hole or welding
  two separate sheets together.
- Normal-flip check: no face incident to the edge may reverse its
  normal after the collapse.

Quad output is a pairing pass after decimation, not a true quad
remesher: adjacent triangles sharing an edge are greedily merged
into quads where the pair is near-planar (normal dot > 0.5). A quad
still counts as 2 triangles toward the budget -- Meshy counts faces
as triangles, and so does count_obj_vertices_triangles().

Honest limits, measured in tests/test_remesh.py (this VM, shared):
- The target is a budget, not a promise: the decimator stops at the
  target when valid collapses remain, and stops early (reporting the
  actual count) when no valid collapse is left.
- Speed: native mesh 4,620 faces -> 1,000 in ~3.1s; a 20,480-face
  icosphere -> 5,000 in ~1.7s; an 81,920-face icosphere -> 30,000
  in ~9.6s. TripoSR scale (~150k faces -> 100k) extrapolates to
  roughly ~20s -- tens of seconds, not minutes, and a remesh runs
  once per generation, async, so that is acceptable. (Profile note:
  the validity checks dominate the cost -- each candidate collapse
  recomputes the normals of its incident faces, ~1.8M _tri_normal
  calls for the native mesh. A per-face normal cache is the known
  optimisation if this ever needs to be faster; it was not done
  in this first build.)
"""

import heapq
import itertools
import shutil
import time

# Meshy's target_polycount range is 100-300,000 faces. The helper
# itself only insists on a mesh that can exist at all (a tetrahedron
# is 4 faces); the HTTP route enforces the Meshy range.
MIN_FACES = 4
MAX_TARGET_FACES = 300000


class RemeshError(ValueError):
    """Raised when a mesh cannot be remeshed (empty, degenerate, bad args)."""


# ---------------------------------------------------------------- OBJ I/O

def read_obj(path):
    """Read a Wavefront OBJ file.

    Returns (vertices, faces): vertices is a list of (x, y, z) float
    tuples, faces a list of int tuples (0-based). 'f' tokens may use
    the v, v/vt, v//vn and v/vt/vn forms, and negative (relative)
    indices. 'vn', 'vt', 'o', 'g', 'usemtl' lines are ignored.
    Polygon faces are kept as-is; decimate() fan-triangulates them.
    """
    vertices = []
    faces = []
    with open(path, 'r', errors='ignore') as f:
        for line in f:
            if line.startswith('v '):
                parts = line.split()
                if len(parts) >= 4:
                    vertices.append((float(parts[1]),
                                     float(parts[2]),
                                     float(parts[3])))
            elif line.startswith('f '):
                idx = []
                for tok in line.split()[1:]:
                    v = tok.split('/')[0]
                    if not v:
                        continue
                    i = int(v)
                    if i < 0:
                        i += len(vertices) + 1
                    idx.append(i - 1)
                if len(idx) >= 3:
                    faces.append(tuple(idx))
    return vertices, faces


def write_obj(path, vertices, faces):
    """Write vertices/faces as OBJ. Triangle faces write as
    'f a b c', quad faces as 'f a b c d'."""
    with open(path, 'w') as f:
        for (x, y, z) in vertices:
            f.write("v %r %r %r\n" % (x, y, z))
        for face in faces:
            f.write("f " + " ".join(str(i + 1) for i in face) + "\n")


def triangle_count(faces):
    """Triangle-equivalent face count: each n-gon contributes n-2."""
    return sum(len(f) - 2 for f in faces if len(f) >= 3)


# ---------------------------------------------------------------- small vector helpers

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


# ---------------------------------------------------------------- quadrics

# A quadric is the 10 unique entries of a symmetric 4x4 matrix:
# (q00, q01, q02, q03, q11, q12, q13, q22, q23, q33).

def _plane_quadric(p0, p1, p2):
    """Quadric of one triangle's plane, or None if degenerate."""
    n = _tri_normal(p0, p1, p2)
    if n is None:
        return None
    a, b, c = n
    d = -(a * p0[0] + b * p0[1] + c * p0[2])
    return (a * a, a * b, a * c, a * d,
            b * b, b * c, b * d,
            c * c, c * d,
            d * d)


def _quad_add(q1, q2):
    return tuple(a + b for a, b in zip(q1, q2))


def _quad_cost_and_position(qu, qv, pu, pv):
    """Cheapest collapse position for edge (u, v) and its cost.

    Q = Qu + Qv. The error-minimising position solves the 3x3 system
    from Q's upper-left block; when that is singular, the midpoint
    and both endpoints are tried and the cheapest wins. Returns
    (cost, (x, y, z)). Cost is the quadric error at that position.
    """
    q = _quad_add(qu, qv)
    q00, q01, q02, q03, q11, q12, q13, q22, q23, q33 = q
    # Determinant of the 3x3 block.
    det = (q00 * (q11 * q22 - q12 * q12)
           - q01 * (q01 * q22 - q12 * q02)
           + q02 * (q01 * q12 - q11 * q02))
    candidates = []
    if abs(det) > 1e-12:
        # Cramer's rule for A x = -[q03, q13, q23].
        rhs = (-q03, -q13, -q23)
        x = (rhs[0] * (q11 * q22 - q12 * q12)
             - q01 * (rhs[1] * q22 - q12 * rhs[2])
             + q02 * (rhs[1] * q12 - q11 * rhs[2])) / det
        y = (q00 * (rhs[1] * q22 - q12 * rhs[2])
             - rhs[0] * (q01 * q22 - q12 * q02)
             + q02 * (q01 * rhs[2] - rhs[1] * q02)) / det
        z = (q00 * (q11 * rhs[2] - rhs[1] * q12)
             - q01 * (q01 * rhs[2] - rhs[1] * q02)
             + rhs[0] * (q01 * q12 - q11 * q02)) / det
        candidates.append((x, y, z))
    candidates.append(((pu[0] + pv[0]) / 2.0,
                       (pu[1] + pv[1]) / 2.0,
                       (pu[2] + pv[2]) / 2.0))
    candidates.append(tuple(pu))
    candidates.append(tuple(pv))

    def cost(p):
        x, y, z = p
        return (q00 * x * x + q11 * y * y + q22 * z * z
                + 2.0 * (q01 * x * y + q02 * x * z + q12 * y * z)
                + 2.0 * (q03 * x + q13 * y + q23 * z) + q33)

    best_p = min(candidates, key=cost)
    return cost(best_p), best_p


# ---------------------------------------------------------------- QEM decimation

def _collapse_valid(u, v, p, pos, face_list, vert_faces, neighbors):
    """Guards for collapsing edge (u, v) to position p (kept at u).

    Link condition: the vertices adjacent to both u and v must number
    exactly the faces the edge belongs to -- otherwise the collapse
    would punch a hole or weld two sheets. Normal-flip check: no
    incident face may reverse its normal.
    """
    shared = vert_faces[u] & vert_faces[v]
    common = (neighbors[u] & neighbors[v]) - {u, v}
    if len(common) != len(shared):
        return False
    for fi in vert_faces[u] | vert_faces[v]:
        f = face_list[fi]
        if f is None:
            continue
        if u in f and v in f:
            continue  # removed by the collapse itself
        old_n = _tri_normal(pos[f[0]], pos[f[1]], pos[f[2]])
        if old_n is None:
            continue
        new_pts = [p if x in (u, v) else pos[x] for x in f]
        new_n = _tri_normal(*new_pts)
        if new_n is None:
            continue  # becomes degenerate, removed -- allowed
        if _dot(old_n, new_n) < 0:
            return False
    return True


def _collapse(u, v, p, pos, quad, face_list, face_keys,
              vert_faces, neighbors, alive):
    """Commit the collapse of v into u at position p. Returns the
    number of faces removed (the faces on the edge, plus any that
    become duplicates of an existing face)."""
    removed = 0
    pos[u] = list(p)
    quad[u] = _quad_add(quad[u], quad[v])
    for fi in list(vert_faces[v]):
        f = face_list[fi]
        if f is None:
            continue
        if u in f:
            face_list[fi] = None
            face_keys.discard(tuple(sorted(f)))
            vert_faces[u].discard(fi)
            removed += 1
        else:
            new_f = [u if x == v else x for x in f]
            key = tuple(sorted(new_f))
            if key in face_keys:
                face_list[fi] = None
                removed += 1
            else:
                face_keys.discard(tuple(sorted(f)))
                face_keys.add(key)
                face_list[fi] = new_f
                vert_faces[u].add(fi)
                for x in new_f:
                    if x != u:
                        neighbors[x].add(u)
                        neighbors[u].add(x)
    vert_faces[v] = set()
    for w in list(neighbors[v]):
        neighbors[w].discard(v)
        if w != u:
            neighbors[w].add(u)
            neighbors[u].add(w)
    neighbors[v] = set()
    neighbors[u].discard(u)
    neighbors[u].discard(v)
    alive[v] = False
    return removed


def decimate(vertices, faces, target_faces):
    """QEM-decimate a mesh to (approximately) target_faces triangles.

    vertices: list of (x, y, z); faces: list of int tuples (polygons
    are fan-triangulated). Returns (new_vertices, new_faces, info)
    where new_faces are triangles and info reports the target, the
    final triangle count, the number of collapses, and elapsed
    seconds. If target_faces >= the input count the mesh is returned
    unchanged (info['decimated'] is False). The target is a budget:
    the loop stops at the target when valid collapses remain, and
    stops early -- reporting the actual count -- when none are left.
    """
    started = time.time()
    # Fan-triangulate polygons, dropping degenerate triangles.
    tris = []
    for f in faces:
        for k in range(1, len(f) - 1):
            t = (f[0], f[k], f[k + 1])
            if len(set(t)) == 3:
                tris.append(t)
    if not tris:
        raise RemeshError("Mesh has no triangles to decimate")
    if target_faces >= len(tris):
        return (list(vertices), [list(t) for t in tris],
                {'target_faces': target_faces,
                 'output_faces': len(tris),
                 'collapses': 0,
                 'decimated': False,
                 'seconds': round(time.time() - started, 3)})
    target_faces = max(MIN_FACES, target_faces)

    n = len(vertices)
    pos = [list(v) for v in vertices]
    alive = [True] * n
    quad = [(0.0,) * 10 for _ in range(n)]
    vert_faces = [set() for _ in range(n)]
    neighbors = [set() for _ in range(n)]
    face_list = [None] * len(tris)
    face_keys = set()
    for i, (a, b, c) in enumerate(tris):
        key = tuple(sorted((a, b, c)))
        if key in face_keys:
            continue  # duplicate triangle: dropped
        face_keys.add(key)
        face_list[i] = [a, b, c]
        k = _plane_quadric(pos[a], pos[b], pos[c])
        if k is not None:
            for v in (a, b, c):
                quad[v] = _quad_add(quad[v], k)
        for v in (a, b, c):
            vert_faces[v].add(i)
        neighbors[a] |= {b, c}
        neighbors[b] |= {a, c}
        neighbors[c] |= {a, b}
    face_count = sum(1 for f in face_list if f is not None)

    def edge_cost(u, v):
        return _quad_cost_and_position(quad[u], quad[v], pos[u], pos[v])

    heap = []
    counter = itertools.count()
    seen_edges = set()
    for f in face_list:
        if f is None:
            continue
        for (u, v) in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
            e = (u, v) if u < v else (v, u)
            if e in seen_edges:
                continue
            seen_edges.add(e)
            c, _ = edge_cost(u, v)
            heapq.heappush(heap, (c, next(counter), u, v))

    collapses = 0
    while face_count > target_faces and heap:
        cost, _, u, v = heapq.heappop(heap)
        if not alive[u] or not alive[v]:
            continue
        if v not in neighbors[u]:
            continue
        # Lazy recomputation: a heap entry priced before a neighbour
        # moved is stale. Re-price; if it moved, re-queue fresh.
        c2, p = edge_cost(u, v)
        if abs(c2 - cost) > 1e-9 * max(1.0, abs(cost)):
            heapq.heappush(heap, (c2, next(counter), u, v))
            continue
        if not _collapse_valid(u, v, p, pos, face_list,
                               vert_faces, neighbors):
            continue
        face_count -= _collapse(u, v, p, pos, quad, face_list,
                                face_keys, vert_faces, neighbors, alive)
        collapses += 1
        for w in list(neighbors[u]):
            c3, _ = edge_cost(u, w)
            heapq.heappush(heap, (c3, next(counter), u, w))

    # Compact: drop dead vertices and removed faces, reindex.
    index = {}
    new_vertices = []
    for i, a in enumerate(alive):
        if a:
            index[i] = len(new_vertices)
            new_vertices.append(tuple(pos[i]))
    new_faces = []
    for f in face_list:
        if f is None or len(set(f)) != 3:
            continue
        new_faces.append((index[f[0]], index[f[1]], index[f[2]]))
    return (new_vertices, new_faces,
            {'target_faces': target_faces,
             'output_faces': len(new_faces),
             'collapses': collapses,
             'decimated': True,
             'seconds': round(time.time() - started, 3)})


# ---------------------------------------------------------------- quad pairing

def merge_to_quads(vertices, faces):
    """Greedily merge adjacent triangle pairs into quads.

    Each triangle tries its three edges; a neighbour across an edge
    is merged when the pair is near-planar (normal dot > 0.5) and
    neither triangle is already used. The best (most planar) edge
    wins per triangle. Returns (faces, quad_count) where faces mixes
    4-tuples (quads) and 3-tuples (leftover triangles). The
    triangle-equivalent face count is unchanged by pairing.
    """
    tris = []
    for f in faces:
        for k in range(1, len(f) - 1):
            t = (f[0], f[k], f[k + 1])
            if len(set(t)) == 3:
                tris.append(t)
    normals = [_tri_normal(vertices[a], vertices[b], vertices[c])
               for (a, b, c) in tris]
    edge_faces = {}
    for i, (a, b, c) in enumerate(tris):
        for e in ((a, b), (b, c), (c, a)):
            edge_faces.setdefault((min(e), max(e)), []).append(i)
    used = [False] * len(tris)
    out = []
    quads = 0
    for i, t in enumerate(tris):
        if used[i]:
            continue
        best = None  # (dot, j, quad)
        for k in range(3):
            e = (t[k], t[(k + 1) % 3])
            for j in edge_faces.get((min(e), max(e)), []):
                if j == i or used[j]:
                    continue
                ni, nj = normals[i], normals[j]
                if ni is None or nj is None:
                    continue
                dot = _dot(ni, nj)
                if dot <= 0.5:
                    continue
                if best is not None and dot <= best[0]:
                    continue
                shared = set(t) & set(tris[j])
                p = next(x for x in t if x not in shared)
                q = next(x for x in tris[j] if x not in shared)
                cyc = [t[0], t[1], t[2], t[0]]
                for m in range(3):
                    if {cyc[m], cyc[m + 1]} == shared:
                        x, y = cyc[m], cyc[m + 1]
                        break
                best = (dot, j, (p, x, q, y))
        if best is not None:
            _, j, quad = best
            used[i] = used[j] = True
            out.append(quad)
            quads += 1
        else:
            used[i] = True
            out.append(t)
    return out, quads


# ---------------------------------------------------------------- high-level entry

def remesh_obj(input_path, output_path, target_faces, topology='triangle'):
    """Remesh the OBJ at input_path to target_faces and write output_path.

    topology 'triangle' writes triangles; 'quad' pairs adjacent
    triangles into quads afterwards (triangle-equivalent count
    unchanged). Returns a dict with input/output vertex and face
    counts (faces counted as triangles, Meshy-style), the target, the
    topology, whether decimation ran, the collapse count, the output
    path, and elapsed seconds. When target_faces >= the input count
    the file is copied through unchanged (decimated False) -- asking
    for more faces than the mesh has is a no-op, not an error.
    Raises RemeshError for a bad topology, a target below MIN_FACES,
    or an empty/degenerate input mesh.
    """
    started = time.time()
    if topology not in ('triangle', 'quad'):
        raise RemeshError(
            "Unsupported topology: %r (allowed: triangle, quad)" % topology)
    if target_faces < MIN_FACES:
        raise RemeshError(
            "target_faces must be >= %d" % MIN_FACES)
    try:
        vertices, faces = read_obj(input_path)
    except OSError as e:
        raise RemeshError("Cannot read %s: %s" % (input_path, e))
    if not vertices or not faces:
        raise RemeshError("No mesh found in %s" % input_path)
    in_faces = triangle_count(faces)
    if in_faces == 0:
        raise RemeshError("Mesh in %s has no faces" % input_path)
    if target_faces >= in_faces:
        shutil.copyfile(input_path, output_path)
        return {
            'input_vertices': len(vertices),
            'input_faces': in_faces,
            'output_vertices': len(vertices),
            'output_faces': in_faces,
            'output_quad_faces': 0,
            'target_faces': target_faces,
            'topology': topology,
            'decimated': False,
            'collapses': 0,
            'output_path': output_path,
            'seconds': round(time.time() - started, 3),
        }
    new_vertices, new_faces, info = decimate(vertices, faces, target_faces)
    n_quads = 0
    if topology == 'quad':
        new_faces, n_quads = merge_to_quads(new_vertices, new_faces)
    write_obj(output_path, new_vertices, new_faces)
    # Verify from disk, so the reported counts are the file's counts.
    v2, f2 = read_obj(output_path)
    return {
        'input_vertices': len(vertices),
        'input_faces': in_faces,
        'output_vertices': len(v2),
        'output_faces': triangle_count(f2),
        'output_quad_faces': n_quads,
        'target_faces': target_faces,
        'topology': topology,
        'decimated': True,
        'collapses': info['collapses'],
        'output_path': output_path,
        'seconds': round(time.time() - started, 3),
    }
