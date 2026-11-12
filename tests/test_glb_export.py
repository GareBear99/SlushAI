#!/usr/bin/env python3
"""Unit tests for src.ai3d.utils.export_glb (local GLB export,
Meshy export equivalent, local + free).

Run from pkg/: python3 test_glb_export.py (exit 0 = all pass). No
server, no Flask, stdlib only. Uses the real native mesh from the
2026-11-11 mesh comparison (~/workspace/slushai-mc-test/native.obj:
4,225 verts / 4,620 faces, open heightfield) as the ground-truth
fixture when present, plus a synthetic subdivided icosphere for
scale. The GLB is verified by an INDEPENDENT parse here (struct +
json straight off the file) -- not by the module's own reader -- so
a writer bug cannot hide behind its own verifier. Timing is
printed, not asserted hard -- this VM is shared and slow.
"""
import json
import math
import os
import struct
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.ai3d.utils.export_glb import (
    GlbExportError,
    export_glb,
    export_glbs_for_generation,
    parse_export_flag,
    read_glb_summary,
    write_glb,
)
from src.ai3d.utils.remesh import remesh_obj

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


def _parse_glb_independent(path):
    """Parse a .glb straight off disk with struct + json. Returns
    (gltf_dict, bin_bytes)."""
    with open(path, 'rb') as f:
        data = f.read()
    magic, version, total = struct.unpack('<III', data[:12])
    assert magic == 0x46546C67, 'bad magic'
    assert version == 2, 'bad version'
    assert total == len(data), 'declared length != file size'
    json_len, json_type = struct.unpack('<II', data[12:20])
    assert json_type == 0x4E4F534A, 'first chunk is not JSON'
    gltf = json.loads(data[20:20 + json_len].decode('utf-8'))
    bin_off = 20 + json_len
    bin_len, bin_type = struct.unpack('<II', data[bin_off:bin_off + 8])
    assert bin_type == 0x004E4942, 'second chunk is not BIN'
    return gltf, data[bin_off + 8:bin_off + 8 + bin_len]


class GlbExportTest(unittest.TestCase):
    def _tmp(self, suffix='.glb'):
        fd, path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        self.addCleanup(os.unlink, path)
        return path

    def _obj_tmp(self):
        return self._tmp(suffix='.obj')

    # --- valid GLB output -------------------------------------------

    def test_glb_valid_native(self):
        if not os.path.exists(NATIVE_OBJ):
            self.skipTest('native.obj fixture absent')
        out = self._tmp()
        started = time.time()
        result = export_glb(NATIVE_OBJ, out)
        elapsed = time.time() - started
        self.assertEqual(result['input_vertices'], 4225)
        self.assertEqual(result['input_faces'], 4620)
        self.assertEqual(result['output_vertices'], 4225)
        self.assertEqual(result['output_faces'], 4620)
        self.assertEqual(result['index_component_type'], 5123)  # uint16
        self.assertEqual(result['glb_bytes'], os.path.getsize(out))

        gltf, bin_data = _parse_glb_independent(out)
        self.assertEqual(gltf['asset']['version'], '2.0')
        self.assertEqual(gltf['scene'], 0)
        acc = gltf['accessors']
        self.assertEqual(acc[0]['count'], 4225)          # POSITION
        self.assertEqual(acc[0]['componentType'], 5126)  # float32
        self.assertEqual(acc[0]['type'], 'VEC3')
        self.assertIn('min', acc[0])
        self.assertIn('max', acc[0])
        self.assertEqual(acc[1]['count'], 4225)          # NORMAL
        self.assertEqual(acc[2]['count'], 4620 * 3)      # indices
        self.assertEqual(acc[2]['componentType'], 5123)
        self.assertEqual(acc[2]['type'], 'SCALAR')
        prim = gltf['meshes'][0]['primitives'][0]
        self.assertEqual(prim['attributes']['POSITION'], 0)
        self.assertEqual(prim['attributes']['NORMAL'], 1)
        self.assertEqual(prim['indices'], 2)

        # Positions round-trip: first vertex in the BIN must match
        # the first 'v ' line of the OBJ (float32 precision).
        with open(NATIVE_OBJ) as f:
            first_v = None
            for line in f:
                if line.startswith('v '):
                    first_v = tuple(float(x) for x in line.split()[1:4])
                    break
        views = gltf['bufferViews']
        pos_off = views[0]['byteOffset']
        px, py, pz = struct.unpack_from('<fff', bin_data, pos_off)
        for got, want in zip((px, py, pz), first_v):
            self.assertAlmostEqual(got, want, places=5)
        # Normals are unit length (spot check the first 100).
        norm_off = views[1]['byteOffset']
        for i in range(100):
            nx, ny, nz = struct.unpack_from(
                '<fff', bin_data, norm_off + 12 * i)
            length = math.sqrt(nx * nx + ny * ny + nz * nz)
            self.assertAlmostEqual(length, 1.0, places=5)
        # Indices are in range.
        idx_off = views[2]['byteOffset']
        idx_fmt = '<%dH' % (4620 * 3)
        indices = struct.unpack_from(idx_fmt, bin_data, idx_off)
        self.assertTrue(all(0 <= i < 4225 for i in indices))
        # Accessor min/max match the OBJ bounds.
        xs, ys, zs = [], [], []
        with open(NATIVE_OBJ) as f:
            for line in f:
                if line.startswith('v '):
                    x, y, z = (float(v) for v in line.split()[1:4])
                    xs.append(x)
                    ys.append(y)
                    zs.append(z)
        for got, want in zip(acc[0]['min'],
                             (min(xs), min(ys), min(zs))):
            self.assertAlmostEqual(got, want, places=5)
        for got, want in zip(acc[0]['max'],
                             (max(xs), max(ys), max(zs))):
            self.assertAlmostEqual(got, want, places=5)
        print("\nnative GLB: %d bytes in %.2fs (%.0f bytes/vertex)"
              % (result['glb_bytes'], elapsed,
                 result['glb_bytes'] / 4225.0))

    def test_glb_summary_reader_agrees(self):
        if not os.path.exists(NATIVE_OBJ):
            self.skipTest('native.obj fixture absent')
        out = self._tmp()
        export_glb(NATIVE_OBJ, out)
        summary = read_glb_summary(out)
        self.assertEqual(summary['version'], 2)
        self.assertEqual(summary['vertices'], 4225)
        self.assertEqual(summary['triangles'], 4620)
        self.assertEqual(summary['index_component_type'], 5123)
        self.assertTrue(summary['has_normals'])
        self.assertEqual(summary['total_bytes'], os.path.getsize(out))

    def test_glb_for_remeshed_mesh(self):
        if not os.path.exists(NATIVE_OBJ):
            self.skipTest('native.obj fixture absent')
        remeshed = self._obj_tmp()
        remesh_obj(NATIVE_OBJ, remeshed, 1000, topology='triangle')
        out = self._tmp()
        result = export_glb(remeshed, out)
        self.assertEqual(result['input_faces'], 1000)
        self.assertEqual(result['output_faces'], 1000)
        self.assertLess(result['output_vertices'], 4225)
        gltf, _ = _parse_glb_independent(out)
        self.assertEqual(gltf['accessors'][0]['count'],
                         result['output_vertices'])
        self.assertEqual(gltf['accessors'][2]['count'], 1000 * 3)

    def test_glb_for_quad_remeshed_mesh(self):
        if not os.path.exists(NATIVE_OBJ):
            self.skipTest('native.obj fixture absent')
        remeshed = self._obj_tmp()
        info = remesh_obj(NATIVE_OBJ, remeshed, 1000, topology='quad')
        self.assertGreater(info['output_quad_faces'], 0)
        out = self._tmp()
        result = export_glb(remeshed, out)
        # Quad faces fan-triangulate back to the same triangle count.
        self.assertEqual(result['output_faces'], 1000)
        gltf, _ = _parse_glb_independent(out)
        self.assertEqual(gltf['accessors'][2]['count'], 1000 * 3)

    def test_glb_icosphere_scale(self):
        verts, faces = _icosphere(5)  # 20,480 faces, 10,242 verts
        out = self._tmp()
        started = time.time()
        result = write_glb(out, verts, faces)
        elapsed = time.time() - started
        self.assertEqual(result['output_vertices'], 10242)
        self.assertEqual(result['output_faces'], 20480)
        self.assertEqual(result['index_component_type'], 5123)
        gltf, _ = _parse_glb_independent(out)
        self.assertEqual(gltf['accessors'][2]['count'], 20480 * 3)
        print("\nicosphere GLB: %d faces in %.2fs"
              % (20480, elapsed))

    def test_uint32_indices_above_65535_vertices(self):
        # 65,537 vertices, one triangle: the index buffer must go
        # uint32 even though the triangle itself is tiny.
        verts = [(float(i), 0.0, 0.0) for i in range(65537)]
        out = self._tmp()
        result = write_glb(out, verts, [(0, 1, 2)])
        self.assertEqual(result['index_component_type'], 5125)
        gltf, bin_data = _parse_glb_independent(out)
        self.assertEqual(gltf['accessors'][2]['componentType'], 5125)
        idx_off = gltf['bufferViews'][2]['byteOffset']
        i0, i1, i2 = struct.unpack_from('<III', bin_data, idx_off)
        self.assertEqual((i0, i1, i2), (0, 1, 2))

    # --- flag + task wiring -----------------------------------------

    def test_parse_export_flag(self):
        for true_val in ('true', 'True', 'TRUE', '1', 'yes', 'Yes', 'on'):
            self.assertTrue(parse_export_flag(true_val), true_val)
        for false_val in ('false', 'False', '0', 'no', 'off', '', None):
            self.assertFalse(parse_export_flag(false_val), false_val)
        for bad_val in ('maybe', '2', 'y', 't'):
            with self.assertRaises(ValueError, msg=bad_val):
                parse_export_flag(bad_val)

    def test_flag_off_writes_nothing(self):
        if not os.path.exists(NATIVE_OBJ):
            self.skipTest('native.obj fixture absent')
        from pathlib import Path
        warnings = []
        result = export_glbs_for_generation(
            Path(NATIVE_OBJ), None, False, warnings.append)
        self.assertEqual(result, {'glb_path': None, 'glb_bytes': None,
                                  'remeshed_glb_path': None,
                                  'remeshed_glb_bytes': None})
        self.assertEqual(warnings, [])
        # No .glb appeared next to the fixture.
        self.assertFalse(
            os.path.exists(NATIVE_OBJ.replace('.obj', '.glb')))

    def test_flag_on_writes_glb(self):
        if not os.path.exists(NATIVE_OBJ):
            self.skipTest('native.obj fixture absent')
        from pathlib import Path
        import shutil
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir)
        obj = os.path.join(tmpdir, 'model_preview.obj')
        shutil.copyfile(NATIVE_OBJ, obj)
        warnings = []
        result = export_glbs_for_generation(
            Path(obj), None, True, warnings.append)
        self.assertEqual(warnings, [])
        self.assertIsNotNone(result['glb_path'])
        self.assertEqual(result['glb_bytes'],
                         os.path.getsize(result['glb_path']))
        self.assertTrue(str(result['glb_path']).endswith(
            'model_preview.glb'))
        self.assertIsNone(result['remeshed_glb_path'])
        self.assertIsNone(result['remeshed_glb_bytes'])
        summary = read_glb_summary(str(result['glb_path']))
        self.assertEqual(summary['vertices'], 4225)
        self.assertEqual(summary['triangles'], 4620)

    def test_flag_on_with_remesh_exports_both(self):
        if not os.path.exists(NATIVE_OBJ):
            self.skipTest('native.obj fixture absent')
        from pathlib import Path
        import shutil
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir)
        obj = os.path.join(tmpdir, 'model_preview.obj')
        remeshed = os.path.join(tmpdir, 'model_preview_remeshed.obj')
        shutil.copyfile(NATIVE_OBJ, obj)
        remesh_obj(NATIVE_OBJ, remeshed, 1000, topology='triangle')
        warnings = []
        result = export_glbs_for_generation(
            Path(obj), Path(remeshed), True, warnings.append)
        self.assertEqual(warnings, [])
        self.assertIsNotNone(result['glb_path'])
        self.assertIsNotNone(result['remeshed_glb_path'])
        self.assertTrue(str(result['remeshed_glb_path']).endswith(
            'model_preview_remeshed.glb'))
        self.assertEqual(
            read_glb_summary(str(result['remeshed_glb_path']))['triangles'],
            1000)
        self.assertEqual(
            read_glb_summary(str(result['glb_path']))['triangles'], 4620)

    def test_export_failure_does_not_raise(self):
        # The generation must never fail because its GLB export did:
        # a corrupt/missing mesh logs a warning and leaves every
        # entry None -- the exact code path the executor calls.
        from pathlib import Path
        warnings = []
        result = export_glbs_for_generation(
            Path('/nonexistent/nope.obj'), None, True, warnings.append)
        self.assertEqual(result, {'glb_path': None, 'glb_bytes': None,
                                  'remeshed_glb_path': None,
                                  'remeshed_glb_bytes': None})
        self.assertEqual(len(warnings), 1)
        self.assertIn('GLB export failed', warnings[0])

    def test_export_failure_one_side_only(self):
        # Original exports fine, remeshed is corrupt: the good GLB
        # still lands, the bad side warns and stays None.
        if not os.path.exists(NATIVE_OBJ):
            self.skipTest('native.obj fixture absent')
        from pathlib import Path
        import shutil
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir)
        obj = os.path.join(tmpdir, 'model_preview.obj')
        bad = os.path.join(tmpdir, 'model_preview_remeshed.obj')
        shutil.copyfile(NATIVE_OBJ, obj)
        with open(bad, 'w') as f:
            f.write("# nothing here\n")
        warnings = []
        result = export_glbs_for_generation(
            Path(obj), Path(bad), True, warnings.append)
        self.assertIsNotNone(result['glb_path'])
        self.assertIsNone(result['remeshed_glb_path'])
        self.assertEqual(len(warnings), 1)

    # --- errors ---------------------------------------------------------

    def test_missing_input_raises(self):
        with self.assertRaises(GlbExportError):
            export_glb('/nonexistent/nope.obj', self._tmp())

    def test_empty_input_raises(self):
        path = self._obj_tmp()
        with open(path, 'w') as f:
            f.write("# nothing here\n")
        with self.assertRaises(GlbExportError):
            export_glb(path, self._tmp())

    def test_vertices_without_faces_raises(self):
        path = self._obj_tmp()
        with open(path, 'w') as f:
            f.write("v 0 0 0\nv 1 0 0\nv 0 1 0\n")
        with self.assertRaises(GlbExportError):
            export_glb(path, self._tmp())

    def test_write_glb_empty_raises(self):
        with self.assertRaises(GlbExportError):
            write_glb(self._tmp(), [], [])

    def test_summary_reader_rejects_non_glb(self):
        path = self._obj_tmp()
        with open(path, 'w') as f:
            f.write("v 0 0 0\n")
        with self.assertRaises(GlbExportError):
            read_glb_summary(path)


if __name__ == '__main__':
    unittest.main(verbosity=2)
