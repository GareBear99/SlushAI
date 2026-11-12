#!/usr/bin/env python3
"""Unit tests for src.ai3d.utils.remesh (local remesh / decimation
to a target face budget) and the triangle-equivalent counter in
mesh_stats.

Run from pkg/: python3 test_remesh.py (exit 0 = all pass). No
server, no Flask, stdlib only. Uses the real native mesh from the
2026-11-11 mesh comparison (~/workspace/slushai-mc-test/native.obj:
4,225 verts / 4,620 faces, open heightfield) as the ground-truth
fixture when present, plus a synthetic subdivided icosphere for
scale. Timing is printed, not asserted hard -- this VM is shared
and slow; the scale test asserts completion, the numbers go in the
write-up.
"""
import math
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.ai3d.utils.mesh_stats import (
    count_obj_vertices_faces,
    count_obj_vertices_triangles,
)
from src.ai3d.utils.remesh import (
    RemeshError,
    decimate,
    merge_to_quads,
    read_obj,
    remesh_obj,
    triangle_count,
    write_obj,
)

NATIVE_OBJ = '/home/hatch/workspace/slushai-mc-test/native.obj'


def _icosphere(subdivisions):
    """Subdivided icosahedron (unit sphere), stdlib only. Returns
    (vertices, faces). 20 faces * 4**subdivisions."""
    t = (1.0 + math.sqrt(5.0)) / 2.0
    verts = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0),
             (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
             (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    verts = [tuple(c / math.sqrt(sum(x * x for x in p)) for c in p)
             for p in verts]
    faces = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11),
             (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6), (7, 1, 8),
             (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9),
             (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    for _ in range(subdivisions):
        cache = {}
        new_faces = []

        def midpoint(a, b):
            key = (min(a, b), max(a, b))
            if key in cache:
                return cache[key]
            pa, pb = verts[a], verts[b]
            m = tuple((pa[i] + pb[i]) / 2.0 for i in range(3))
            n = math.sqrt(sum(c * c for c in m))
            verts.append(tuple(c / n for c in m))
            cache[key] = len(verts) - 1
            return cache[key]

        for (a, b, c) in faces:
            ab, bc, ca = midpoint(a, b), midpoint(b, c), midpoint(c, a)
            new_faces += [(a, ab, ca), (b, bc, ab), (c, ca, bc),
                          (ab, bc, ca)]
        faces = new_faces
    return verts, faces


class RemeshTest(unittest.TestCase):
    def _tmp(self, suffix='.obj'):
        fd, path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        self.addCleanup(os.unlink, path)
        return path

    def _within_budget(self, actual, target, pct=0.02):
        # A decimator budgets, it does not promise exactness: the
        # last collapse can overshoot by a face, and a mesh can run
        # out of valid collapses. Within 2% of target is a hit.
        self.assertLessEqual(actual, target)
        self.assertGreaterEqual(actual, target * (1.0 - pct))

    # --- I/O and counting -------------------------------------------

    def test_read_write_roundtrip_native(self):
        if not os.path.exists(NATIVE_OBJ):
            self.skipTest('native.obj fixture absent')
        vertices, faces = read_obj(NATIVE_OBJ)
        self.assertEqual(len(vertices), 4225)
        self.assertEqual(triangle_count(faces), 4620)
        out = self._tmp()
        write_obj(out, vertices, faces)
        v2, f2 = read_obj(out)
        self.assertEqual(len(v2), 4225)
        self.assertEqual(triangle_count(f2), 4620)

    def test_triangle_counter_counts_quads_as_two(self):
        path = self._tmp()
        with open(path, 'w') as f:
            f.write("v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nv 0 0 1\n")
            f.write("f 1 2 3\nf 1 3 4\nf 1 2 3 4\n")
        # 2 triangle lines + 1 quad line: 3 faces, 4 triangles.
        self.assertEqual(count_obj_vertices_faces(path), (5, 3))
        self.assertEqual(count_obj_vertices_triangles(path), (5, 4))

    # --- decimation --------------------------------------------------

    def test_decimate_native_to_1000(self):
        if not os.path.exists(NATIVE_OBJ):
            self.skipTest('native.obj fixture absent')
        out = self._tmp()
        result = remesh_obj(NATIVE_OBJ, out, 1000, topology='triangle')
        self.assertTrue(result['decimated'])
        self.assertEqual(result['input_vertices'], 4225)
        self.assertEqual(result['input_faces'], 4620)
        self._within_budget(result['output_faces'], 1000)
        self.assertLess(result['output_vertices'], 4225)
        self.assertGreater(result['collapses'], 0)
        print("\nnative 4620 -> %d faces in %.2fs"
              % (result['output_faces'], result['seconds']))

    def test_decimate_native_to_100(self):
        if not os.path.exists(NATIVE_OBJ):
            self.skipTest('native.obj fixture absent')
        out = self._tmp()
        result = remesh_obj(NATIVE_OBJ, out, 100, topology='triangle')
        self._within_budget(result['output_faces'], 100)
        print("native 4620 -> %d faces in %.2fs"
              % (result['output_faces'], result['seconds']))

    def test_counts_match_disk(self):
        if not os.path.exists(NATIVE_OBJ):
            self.skipTest('native.obj fixture absent')
        out = self._tmp()
        result = remesh_obj(NATIVE_OBJ, out, 1000, topology='triangle')
        # The counts the helper reports must be the file's counts.
        self.assertEqual(count_obj_vertices_triangles(out),
                         (result['output_vertices'],
                          result['output_faces']))
        self.assertEqual(count_obj_vertices_faces(out),
                         (result['output_vertices'],
                          result['output_faces']))

    def test_quad_mode(self):
        if not os.path.exists(NATIVE_OBJ):
            self.skipTest('native.obj fixture absent')
        out = self._tmp()
        result = remesh_obj(NATIVE_OBJ, out, 1000, topology='quad')
        self._within_budget(result['output_faces'], 1000)
        self.assertGreater(result['output_quad_faces'], 0)
        # Quad faces collapse 2 triangles into 1 f-line, so the
        # f-line count is strictly below the triangle count.
        f_verts, f_lines = count_obj_vertices_faces(out)
        self.assertEqual(f_verts, result['output_vertices'])
        self.assertLess(f_lines, result['output_faces'])
        self.assertEqual(count_obj_vertices_triangles(out),
                         (result['output_vertices'],
                          result['output_faces']))
        print("quad mode: %d quad faces, %d f-lines for %d triangles"
              % (result['output_quad_faces'], f_lines,
                 result['output_faces']))

    def test_quad_pairing_keeps_triangle_budget(self):
        # merge_to_quads alone: pairing must not change the
        # triangle-equivalent count.
        verts, faces = _icosphere(2)  # 320 faces
        paired, n_quads = merge_to_quads(verts, faces)
        self.assertEqual(triangle_count(paired), triangle_count(faces))
        self.assertGreater(n_quads, 0)

    # --- no-op / un-remeshed path ------------------------------------

    def test_noop_when_target_above_input(self):
        if not os.path.exists(NATIVE_OBJ):
            self.skipTest('native.obj fixture absent')
        out = self._tmp()
        result = remesh_obj(NATIVE_OBJ, out, 10000, topology='triangle')
        self.assertFalse(result['decimated'])
        self.assertEqual(result['output_vertices'], 4225)
        self.assertEqual(result['output_faces'], 4620)
        with open(NATIVE_OBJ, 'rb') as f:
            orig = f.read()
        with open(out, 'rb') as f:
            copied = f.read()
        self.assertEqual(copied, orig)

    def test_decimate_noop_at_exact_input_count(self):
        verts, faces = _icosphere(1)  # 80 faces
        v2, f2, info = decimate(verts, faces, 80)
        self.assertFalse(info['decimated'])
        self.assertEqual(info['output_faces'], 80)

    # --- scale ---------------------------------------------------------

    def test_icosphere_20k_to_5k(self):
        verts, faces = _icosphere(5)  # 20,480 faces
        self.assertEqual(len(faces), 20480)
        started = time.time()
        v2, f2, info = decimate(verts, faces, 5000)
        elapsed = time.time() - started
        self._within_budget(info['output_faces'], 5000)
        # Output must be a valid mesh: distinct indices, in range.
        for tri in f2:
            self.assertEqual(len(set(tri)), 3)
            for idx in tri:
                self.assertGreaterEqual(idx, 0)
                self.assertLess(idx, len(v2))
        print("\nicosphere 20480 -> %d faces in %.2fs (%.0f faces/s)"
              % (info['output_faces'], elapsed,
                 20480 / max(elapsed, 1e-9)))

    # --- errors ---------------------------------------------------------

    def test_empty_input_raises(self):
        path = self._tmp()
        with open(path, 'w') as f:
            f.write("# nothing here\n")
        with self.assertRaises(RemeshError):
            remesh_obj(path, self._tmp(), 100)

    def test_missing_input_raises(self):
        with self.assertRaises(RemeshError):
            remesh_obj('/nonexistent/nope.obj', self._tmp(), 100)

    def test_bad_target_raises(self):
        if not os.path.exists(NATIVE_OBJ):
            self.skipTest('native.obj fixture absent')
        with self.assertRaises(RemeshError):
            remesh_obj(NATIVE_OBJ, self._tmp(), 3)

    def test_bad_topology_raises(self):
        if not os.path.exists(NATIVE_OBJ):
            self.skipTest('native.obj fixture absent')
        with self.assertRaises(RemeshError):
            remesh_obj(NATIVE_OBJ, self._tmp(), 100, topology='hexagon')


if __name__ == '__main__':
    unittest.main(verbosity=2)
