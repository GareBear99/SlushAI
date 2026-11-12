#!/usr/bin/env python3
"""Unit tests for src.ai3d.utils.mesh_stats (OBJ vertex/face counts).

Run: python3 tests/test_mesh_stats.py (exit 0 = all pass). No server,
no Flask, stdlib only. Uses the real native mesh from the 2026-11-11
mesh comparison (~/workspace/slushai-mc-test/native.obj) as the
ground-truth fixture when present, plus synthetic OBJs.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.ai3d.utils.mesh_stats import (
    count_obj_vertices_faces,
    count_obj_vertices_triangles,
)

NATIVE_OBJ = '/home/hatch/workspace/slushai-mc-test/native.obj'


class MeshStatsTest(unittest.TestCase):
    def _write(self, text):
        fd, path = tempfile.mkstemp(suffix='.obj')
        with os.fdopen(fd, 'w') as f:
            f.write(text)
        self.addCleanup(os.unlink, path)
        return path

    def test_counts_vertices_and_faces(self):
        path = self._write(
            '# test\n'
            'v 0 0 0\nv 1 0 0\nv 0 1 0\n'
            'vn 0 0 1\nvt 0 0\n'
            'f 1 2 3\nf 1 3 2\n')
        self.assertEqual(count_obj_vertices_faces(path), (3, 2))

    def test_normals_and_uvs_are_not_vertices(self):
        path = self._write('vn 0 0 1\nvn 0 1 0\nvt 0.5 0.5\n')
        self.assertEqual(count_obj_vertices_faces(path), (0, 0))

    def test_missing_file_returns_zero(self):
        self.assertEqual(
            count_obj_vertices_faces('/nonexistent/nope.obj'), (0, 0))

    def test_empty_file_returns_zero(self):
        self.assertEqual(count_obj_vertices_faces(self._write('')), (0, 0))

    def test_real_native_mesh(self):
        if not os.path.exists(NATIVE_OBJ):
            self.skipTest('native.obj fixture absent')
        vertices, faces = count_obj_vertices_faces(NATIVE_OBJ)
        # The recorded live native mesh: 4,225 vertices, 4,620 faces.
        self.assertEqual(vertices, 4225)
        self.assertEqual(faces, 4620)

    def test_triangles_counts_quads_as_two(self):
        path = self._write(
            "v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nv 0 0 1\n"
            "f 1 2 3\nf 1 3 4\nf 1 2 3 4\n")
        # 2 triangle lines + 1 quad line: 3 faces, 4 triangles.
        self.assertEqual(count_obj_vertices_triangles(path), (5, 4))

    def test_triangles_equals_faces_on_triangles_only(self):
        if not os.path.exists(NATIVE_OBJ):
            self.skipTest('native.obj fixture absent')
        self.assertEqual(count_obj_vertices_triangles(NATIVE_OBJ), (4225, 4620))

    def test_triangles_missing_file_returns_zero(self):
        self.assertEqual(
            count_obj_vertices_triangles('/nonexistent/nope.obj'), (0, 0))


if __name__ == '__main__':
    unittest.main(verbosity=2)
