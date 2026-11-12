"""Mesh statistics for SlushAI generation results.

Vertex/face counts are the numbers Meshy surfaces on every task object
(Remesh targets a face count; the web app shows vertices/faces per
model). SlushAI counted them only in /api/models. This module is the
single place that counts them, so the generation task result can carry
the same numbers the model list does.

Stdlib only, so it is importable without the Flask app.
"""


def count_obj_vertices_faces(path):
    """Count vertices and faces in a Wavefront OBJ file.

    Counts lines starting with 'v ' (vertices) and 'f ' (faces).
    'vn ' (normals) and 'vt ' (UVs) are not vertices and are not
    counted. Returns (0, 0) for a missing or unreadable file — this
    is reporting data, never a reason to fail a generation.
    """
    vertices = 0
    faces = 0
    try:
        with open(path, 'r', errors='ignore') as f:
            for line in f:
                if line.startswith('v '):
                    vertices += 1
                elif line.startswith('f '):
                    faces += 1
    except (OSError, ValueError):
        return 0, 0
    return vertices, faces


def count_obj_vertices_triangles(path):
    """Count vertices and triangle-equivalent faces in an OBJ file.

    Each 'f ' line contributes (verts_in_face - 2) triangles, so a
    quad face counts as 2 and a triangle as 1. For triangle-only
    files this equals count_obj_vertices_faces. This is the count a
    remesh target is measured against -- Meshy counts faces as
    triangles, and a quad-mode remesh still budgets in triangles.
    Returns (0, 0) for a missing or unreadable file.
    """
    vertices = 0
    triangles = 0
    try:
        with open(path, 'r', errors='ignore') as f:
            for line in f:
                if line.startswith('v '):
                    vertices += 1
                elif line.startswith('f '):
                    n = len(line.split()) - 1
                    if n >= 3:
                        triangles += n - 2
    except (OSError, ValueError):
        return 0, 0
    return vertices, triangles
