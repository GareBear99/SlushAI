#!/usr/bin/env python3
"""Unit tests for src.ai3d.utils.pbr_textures (local PBR textures,
Meshy PBR-texture equivalent, local + free).

Run from pkg/: python3 test_pbr_textures.py (exit 0 = all pass). No
server, no Flask, stdlib only. Uses the real native mesh from the
2026-11-11 mesh comparison (~/workspace/slushai-mc-test/native.obj:
4,225 verts / 4,620 faces, open heightfield) as the ground-truth
fixture when present, plus a synthetic subdivided icosphere. PNGs
are verified by an INDEPENDENT decode here (zlib + struct straight
off the file) and GLBs by an INDEPENDENT parse (struct + json) --
not by the module's own encoder or reader -- so a writer bug cannot
hide behind its own verifier. Timing is printed, not asserted hard
-- this VM is shared and slow.
"""
import binascii
import json
import math
import os
import struct
import sys
import tempfile
import time
import unittest
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.ai3d.utils.export_glb import export_glb
from src.ai3d.utils.pbr_textures import (
    PbrError,
    apply_pbr_for_generation,
    compute_uvs,
    compute_vertex_features,
    embed_pbr_in_glb,
    encode_png_rgb,
    generate_pbr_for_obj,
    make_basecolor_png,
    make_metallic_roughness_png,
    parse_pbr_flag,
    write_textured_obj,
)
from src.ai3d.utils.remesh import read_obj, remesh_obj

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


def _write_obj_tmp(path, vertices, faces):
    with open(path, 'w') as f:
        for (x, y, z) in vertices:
            f.write("v %r %r %r\n" % (x, y, z))
        for face in faces:
            f.write("f " + " ".join(str(i + 1) for i in face) + "\n")


def _decode_png_independent(data):
    """Decode a PNG straight off disk with zlib + struct. Returns
    (width, height, rows) where rows are lists of (r, g, b) tuples.
    Verifies the signature, IHDR fields, chunk CRCs, and that every
    scanline uses filter 0."""
    assert data[:8] == b'\x89PNG\r\n\x1a\n', 'bad PNG signature'
    off = 8
    idat = b''
    width = height = None
    while off < len(data):
        length, ctype = struct.unpack('>I4s', data[off:off + 8])
        chunk = data[off + 8:off + 8 + length]
        crc_stored, = struct.unpack('>I', data[off + 8 + length:
                                                off + 12 + length])
        crc_calc = binascii.crc32(ctype + chunk) & 0xFFFFFFFF
        assert crc_stored == crc_calc, 'bad chunk CRC for %r' % ctype
        if ctype == b'IHDR':
            width, height, depth, color, comp, filt, inter = struct.unpack(
                '>IIBBBBB', chunk)
            assert depth == 8 and color == 2, 'not 8-bit RGB'
            assert comp == 0 and filt == 0 and inter == 0
        elif ctype == b'IDAT':
            idat += chunk
        elif ctype == b'IEND':
            break
        off += 12 + length
    assert width is not None, 'no IHDR'
    raw = zlib.decompress(idat)
    assert len(raw) == height * (1 + width * 3), 'bad IDAT size'
    rows = []
    pos = 0
    for _ in range(height):
        assert raw[pos] == 0, 'scanline filter is not 0'
        pos += 1
        row = []
        for _ in range(width):
            row.append((raw[pos], raw[pos + 1], raw[pos + 2]))
            pos += 3
        rows.append(row)
    return width, height, rows


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


class PbrTexturesTest(unittest.TestCase):
    def _tmp(self, suffix='.png'):
        fd, path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        self.addCleanup(os.unlink, path)
        return path

    def _obj_tmp(self):
        return self._tmp(suffix='.obj')

    def _native(self):
        if not os.path.exists(NATIVE_OBJ):
            self.skipTest('native.obj fixture absent')
        return read_obj(NATIVE_OBJ)

    # --- UVs ------------------------------------------------------

    def test_uvs_in_unit_square_native(self):
        vertices, faces = self._native()
        uvs = compute_uvs(vertices, faces)
        self.assertEqual(len(uvs), 4225)
        for (u, v) in uvs:
            self.assertGreaterEqual(u, 0.0)
            self.assertLessEqual(u, 1.0)
            self.assertGreaterEqual(v, 0.0)
            self.assertLessEqual(v, 1.0)
        us = [u for (u, _) in uvs]
        vs = [v for (_, v) in uvs]
        self.assertAlmostEqual(min(us), 0.0, places=6)
        self.assertAlmostEqual(max(us), 1.0, places=6)
        self.assertAlmostEqual(min(vs), 0.0, places=6)
        self.assertAlmostEqual(max(vs), 1.0, places=6)

    def test_uvs_count_matches_vertices_icosphere(self):
        vertices, faces = _icosphere(2)
        uvs = compute_uvs(vertices, faces)
        self.assertEqual(len(uvs), len(vertices))
        for (u, v) in uvs:
            self.assertTrue(0.0 <= u <= 1.0 and 0.0 <= v <= 1.0)

    def test_vertex_features_in_unit_range(self):
        vertices, faces = self._native()
        heights, slopes = compute_vertex_features(vertices, faces)
        self.assertEqual(len(heights), 4225)
        self.assertEqual(len(slopes), 4225)
        self.assertTrue(all(0.0 <= h <= 1.0 for h in heights))
        self.assertTrue(all(0.0 <= s <= 1.0 for s in slopes))
        # A heightfield has both flat ground and steep sides.
        self.assertLess(min(heights), 0.05)
        self.assertGreater(max(heights), 0.95)
        self.assertGreater(max(slopes), 0.5)

    # --- PNG encoder ----------------------------------------------

    def test_png_encoder_roundtrip(self):
        rows = [[(255, 0, 0), (0, 255, 0)],
                [(0, 0, 255), (17, 34, 51)]]
        data = encode_png_rgb(2, 2, rows)
        width, height, back = _decode_png_independent(data)
        self.assertEqual((width, height), (2, 2))
        self.assertEqual(back, rows)

    def test_png_encoder_rejects_bad_rows(self):
        with self.assertRaises(PbrError):
            encode_png_rgb(2, 2, [[(0, 0, 0)]])
        with self.assertRaises(PbrError):
            encode_png_rgb(2, 2, [[(0, 0, 0), (0, 0, 0)],
                                  [(0, 0, 0)]])

    # --- texture maps ----------------------------------------------

    def test_basecolor_dims_and_deterministic(self):
        vertices, faces = self._native()
        uvs = compute_uvs(vertices, faces)
        png1 = make_basecolor_png(vertices, faces, uvs, 64, seed=3)
        png2 = make_basecolor_png(vertices, faces, uvs, 64, seed=3)
        png3 = make_basecolor_png(vertices, faces, uvs, 64, seed=4)
        self.assertEqual(png1, png2)  # same seed -> identical bytes
        self.assertNotEqual(png1, png3)  # different seed -> different
        width, height, rows = _decode_png_independent(png1)
        self.assertEqual((width, height), (64, 64))
        # Not uniform: the palette + noise must actually vary.
        reds = [px[0] for row in rows for px in row]
        mean = sum(reds) / len(reds)
        var = sum((r - mean) ** 2 for r in reds) / len(reds)
        self.assertGreater(var ** 0.5, 5.0)

    def test_metallic_roughness_channels(self):
        vertices, faces = self._native()
        uvs = compute_uvs(vertices, faces)
        png = make_metallic_roughness_png(vertices, faces, uvs, 64)
        width, height, rows = _decode_png_independent(png)
        self.assertEqual((width, height), (64, 64))
        for row in rows:
            for (r, g, b) in row:
                self.assertEqual(r, 255)  # R unused
                self.assertEqual(b, 0)    # metallic 0: dielectric
                # roughness 0.70-0.95 -> G in [178, 242]
                self.assertGreaterEqual(g, 178)
                self.assertLessEqual(g, 242)

    # --- textured OBJ ----------------------------------------------

    def test_textured_obj_vt_lines(self):
        vertices, faces = self._native()
        uvs = compute_uvs(vertices, faces)
        src = self._obj_tmp()
        dst = self._tmp(suffix='.obj')
        _write_obj_tmp(src, vertices, faces)
        v, uv, f = write_textured_obj(src, dst, uvs)
        self.assertEqual((v, uv), (4225, 4225))
        self.assertEqual(f, 4620)
        vt_lines = 0
        f_vt = 0
        with open(dst, 'r') as fh:
            for line in fh:
                if line.startswith('vt '):
                    vt_lines += 1
                elif line.startswith('f '):
                    self.assertTrue(all('/' in tok
                                        for tok in line.split()[1:]))
                    f_vt += 1
        self.assertEqual(vt_lines, 4225)
        self.assertEqual(f_vt, 4620)
        v2, f2 = read_obj(dst)  # plain reader still sees the mesh
        self.assertEqual(len(v2), 4225)
        self.assertEqual(len(f2), 4620)

    def test_write_textured_obj_uv_mismatch_raises(self):
        vertices, faces = _icosphere(1)
        src = self._obj_tmp()
        _write_obj_tmp(src, vertices, faces)
        with self.assertRaises(PbrError):
            write_textured_obj(src, self._tmp(suffix='.obj'),
                               [(0.0, 0.0)] * 3)

    # --- high-level generation --------------------------------------

    def test_generate_pbr_native(self):
        if not os.path.exists(NATIVE_OBJ):
            self.skipTest('native.obj fixture absent')
        started = time.time()
        info = generate_pbr_for_obj(NATIVE_OBJ, resolution=128)
        elapsed = time.time() - started
        self.assertEqual(info['input_vertices'], 4225)
        self.assertEqual(info['input_faces'], 4620)
        self.assertEqual(info['uv_count'], 4225)
        self.assertEqual(info['resolution'], 128)
        for key in ('textured_path', 'basecolor_path',
                    'metallic_roughness_path'):
            self.assertTrue(os.path.exists(info[key]), key)
            self.addCleanup(os.unlink, info[key])
        self.assertEqual(info['basecolor_bytes'],
                         os.path.getsize(info['basecolor_path']))
        self.assertEqual(info['metallic_roughness_bytes'],
                         os.path.getsize(info['metallic_roughness_path']))
        with open(info['basecolor_path'], 'rb') as fh:
            w, h, _ = _decode_png_independent(fh.read())
        self.assertEqual((w, h), (128, 128))
        print("\nnative PBR (128px): %.2fs, basecolor %d B, MR %d B"
              % (elapsed, info['basecolor_bytes'],
                 info['metallic_roughness_bytes']))

    def test_generate_pbr_icosphere(self):
        vertices, faces = _icosphere(2)
        src = self._obj_tmp()
        _write_obj_tmp(src, vertices, faces)
        info = generate_pbr_for_obj(src, resolution=64)
        self.assertEqual(info['input_vertices'], len(vertices))
        self.assertEqual(info['uv_count'], len(vertices))
        for key in ('textured_path', 'basecolor_path',
                    'metallic_roughness_path'):
            self.assertTrue(os.path.exists(info[key]), key)
            self.addCleanup(os.unlink, info[key])

    def test_generate_pbr_resolution_bounds(self):
        vertices, faces = _icosphere(1)
        src = self._obj_tmp()
        _write_obj_tmp(src, vertices, faces)
        with self.assertRaises(PbrError):
            generate_pbr_for_obj(src, resolution=32)
        with self.assertRaises(PbrError):
            generate_pbr_for_obj(src, resolution=2048)
        info = generate_pbr_for_obj(src, resolution=64)
        self.assertEqual(info['resolution'], 64)
        for key in ('textured_path', 'basecolor_path',
                    'metallic_roughness_path'):
            self.addCleanup(os.unlink, info[key])

    def test_generate_pbr_missing_file_raises(self):
        with self.assertRaises(PbrError):
            generate_pbr_for_obj('/nonexistent/mesh.obj')

    # --- GLB embedding ----------------------------------------------

    def test_embed_pbr_in_glb_native(self):
        if not os.path.exists(NATIVE_OBJ):
            self.skipTest('native.obj fixture absent')
        vertices, faces = read_obj(NATIVE_OBJ)
        uvs = compute_uvs(vertices, faces)
        glb = self._tmp(suffix='.glb')
        export_glb(NATIVE_OBJ, glb)
        gltf_before, _ = _parse_glb_independent(glb)
        pos_before = gltf_before['accessors'][0]
        bc_png = make_basecolor_png(vertices, faces, uvs, 64)
        mr_png = make_metallic_roughness_png(vertices, faces, uvs, 64)
        started = time.time()
        info = embed_pbr_in_glb(glb, uvs, bc_png, mr_png)
        elapsed = time.time() - started
        self.assertEqual(info['uv_count'], 4225)
        self.assertEqual(info['glb_bytes'], os.path.getsize(glb))
        gltf, bin_data = _parse_glb_independent(glb)
        prim = gltf['meshes'][0]['primitives'][0]
        attrs = prim['attributes']
        self.assertIn('TEXCOORD_0', attrs)
        self.assertIn('POSITION', attrs)
        self.assertIn('NORMAL', attrs)
        uv_acc = gltf['accessors'][attrs['TEXCOORD_0']]
        self.assertEqual(uv_acc['count'], 4225)
        self.assertEqual(uv_acc['type'], 'VEC2')
        self.assertEqual(uv_acc['min'], [0.0, 0.0])
        self.assertEqual(uv_acc['max'], [1.0, 1.0])
        # Geometry accessors untouched.
        self.assertEqual(gltf['accessors'][attrs['POSITION']]['count'],
                         4225)
        self.assertEqual(gltf['accessors'][attrs['POSITION']]['min'],
                         pos_before['min'])
        self.assertEqual(gltf['accessors'][attrs['POSITION']]['max'],
                         pos_before['max'])
        self.assertEqual(len(gltf.get('images', [])), 2)
        self.assertTrue(all(im['mimeType'] == 'image/png'
                            for im in gltf['images']))
        self.assertEqual(len(gltf.get('textures', [])), 2)
        self.assertEqual(len(gltf.get('samplers', [])), 1)
        pbr = gltf['materials'][0]['pbrMetallicRoughness']
        self.assertEqual(pbr['baseColorTexture'], {'index': 0})
        self.assertEqual(pbr['metallicRoughnessTexture'], {'index': 1})
        self.assertEqual(pbr['baseColorFactor'], [1.0, 1.0, 1.0, 1.0])
        self.assertEqual(pbr['metallicFactor'], 1.0)
        self.assertEqual(pbr['roughnessFactor'], 1.0)
        # The embedded PNGs decode to the same pixels as the sources.
        for img_idx, src_png in ((0, bc_png), (1, mr_png)):
            bv = gltf['images'][img_idx]['bufferView']
            view = gltf['bufferViews'][bv]
            blob = bin_data[view['byteOffset']:
                            view['byteOffset'] + view['byteLength']]
            w1, h1, rows1 = _decode_png_independent(bytes(blob))
            w2, h2, rows2 = _decode_png_independent(src_png)
            self.assertEqual((w1, h1), (w2, h2))
            self.assertEqual(rows1, rows2)
        print("\nnative GLB embed: %.2fs, %d B total"
              % (elapsed, info['glb_bytes']))

    def test_embed_pbr_uv_mismatch_raises(self):
        if not os.path.exists(NATIVE_OBJ):
            self.skipTest('native.obj fixture absent')
        glb = self._tmp(suffix='.glb')
        export_glb(NATIVE_OBJ, glb)
        with self.assertRaises(PbrError):
            embed_pbr_in_glb(glb, [(0.0, 0.0)] * 10, b'xx', b'yy')

    def test_embed_pbr_missing_glb_raises(self):
        with self.assertRaises(PbrError):
            embed_pbr_in_glb('/nonexistent/model.glb',
                             [(0.0, 0.0)], b'xx', b'yy')

    # --- flag parsing ------------------------------------------------

    def test_parse_pbr_flag(self):
        for v in ('1', 'true', 'TRUE', 'yes', 'on', ' True '):
            self.assertTrue(parse_pbr_flag(v))
        for v in ('0', 'false', 'no', 'off', '', None):
            self.assertFalse(parse_pbr_flag(v))
        with self.assertRaises(ValueError):
            parse_pbr_flag('maybe')

    # --- guarded generation helper -----------------------------------

    def test_apply_flag_off_writes_nothing(self):
        if not os.path.exists(NATIVE_OBJ):
            self.skipTest('native.obj fixture absent')
        warnings = []
        result = apply_pbr_for_generation(
            NATIVE_OBJ, None, {'glb_path': None}, False,
            warnings.append)
        self.assertTrue(all(v is None for k, v in result.items()
                            if not k.endswith('_embedded')))
        self.assertFalse(result['glb_pbr_embedded'])
        self.assertFalse(result['remeshed_glb_pbr_embedded'])
        self.assertEqual(warnings, [])

    def test_apply_flag_on_with_glb(self):
        if not os.path.exists(NATIVE_OBJ):
            self.skipTest('native.obj fixture absent')
        glb = self._tmp(suffix='.glb')
        export_glb(NATIVE_OBJ, glb)
        warnings = []
        result = apply_pbr_for_generation(
            NATIVE_OBJ, None, {'glb_path': glb}, True,
            warnings.append, resolution=64)
        self.assertEqual(warnings, [])
        self.assertEqual(result['uv_count'], 4225)
        self.assertTrue(result['glb_pbr_embedded'])
        for key in ('textured_path', 'basecolor_path',
                    'metallic_roughness_path'):
            self.assertTrue(os.path.exists(result[key]), key)
            self.addCleanup(os.unlink, result[key])
        self.assertEqual(result['basecolor_bytes'],
                         os.path.getsize(result['basecolor_path']))
        gltf, _ = _parse_glb_independent(glb)
        self.assertIn('TEXCOORD_0',
                      gltf['meshes'][0]['primitives'][0]['attributes'])

    def test_apply_bad_obj_never_raises(self):
        warnings = []
        result = apply_pbr_for_generation(
            '/nonexistent/mesh.obj', None, {'glb_path': None}, True,
            warnings.append)
        self.assertEqual(len(warnings), 1)
        self.assertIsNone(result['textured_path'])
        self.assertFalse(result['glb_pbr_embedded'])

    def test_apply_remeshed_variant(self):
        if not os.path.exists(NATIVE_OBJ):
            self.skipTest('native.obj fixture absent')
        remeshed = self._tmp(suffix='.obj')
        remesh_obj(NATIVE_OBJ, remeshed, target_faces=1000)
        rglb = self._tmp(suffix='.glb')
        export_glb(remeshed, rglb)
        warnings = []
        result = apply_pbr_for_generation(
            NATIVE_OBJ, remeshed,
            {'glb_path': None, 'remeshed_glb_path': rglb}, True,
            warnings.append, resolution=64)
        self.assertEqual(warnings, [])
        self.assertEqual(result['uv_count'], 4225)
        self.assertIsNotNone(result['remeshed_textured_path'])
        self.assertIsNotNone(result['remeshed_basecolor_path'])
        self.assertTrue(result['remeshed_glb_pbr_embedded'])
        self.assertFalse(result['glb_pbr_embedded'])  # no main GLB
        for key in ('textured_path', 'basecolor_path',
                    'metallic_roughness_path',
                    'remeshed_textured_path',
                    'remeshed_basecolor_path',
                    'remeshed_metallic_roughness_path'):
            self.assertTrue(os.path.exists(result[key]), key)
            self.addCleanup(os.unlink, result[key])

    def test_full_flow_timing_native(self):
        if not os.path.exists(NATIVE_OBJ):
            self.skipTest('native.obj fixture absent')
        started = time.time()
        info = generate_pbr_for_obj(NATIVE_OBJ, resolution=256)
        for key in ('textured_path', 'basecolor_path',
                    'metallic_roughness_path'):
            self.addCleanup(os.unlink, info[key])
        print("\nnative full PBR 256px: %.2fs (basecolor %d B, MR %d B)"
              % (time.time() - started, info['basecolor_bytes'],
                 info['metallic_roughness_bytes']))


if __name__ == '__main__':
    unittest.main(verbosity=2)
