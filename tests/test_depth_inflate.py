#!/usr/bin/env python3
"""Unit tests for src.ai3d.reconstructors.depth_inflate (native
DepthInflationRunner) — the INVERTED-MASK fix.

Gary, 2026-11-12: "clearly youv got something inverted and wrong."
The old code assumed bright = keep/high, so for a dark subject on a
light background it kept the white background as the sheet and deleted
the disc. Measured on the real assets/example.png with the ORIGINAL
code: 5,652 of 5,696 faces on the background, 44 (0.8%) on the disc;
disc verts at mean height -0.284, background verts at +0.276.

These tests prove the fix from both polarities plus the real image:
dark-disc-on-white and light-disc-on-dark both keep the SUBJECT and
drop the background, and the subject is a raised relief, not a sheet
with a hole.

Run from pkg/: python3 test_depth_inflate.py (exit 0 = all pass).
Needs numpy + Pillow (present in the temp-build venv).
"""
import os
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image, ImageDraw, ImageOps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.ai3d.reconstructors.depth_inflate import (
    DepthInflationRunner,
    _otsu_subject_mask,
    _otsu_threshold,
)

# The real input that exposed the inversion (byte-identical to the Mac's
# /Users/gary/projects/AI3DModeller/assets/example.png, md5 db9b87dd...).
EXAMPLE_PNG = "/home/hatch/workspace/slushai-temp-build/probe/example.png"

SIZE = 256
CENTRE = (SIZE // 2, SIZE // 2)
RADIUS = 60


def make_disc(path, bg_lum, disc_lum, radius=RADIUS, alpha_bg=None):
    """Flat disc on a flat background. alpha_bg=None -> opaque RGBA;
    otherwise an RGBA image whose background is transparent."""
    if alpha_bg is None:
        im = Image.new("RGBA", (SIZE, SIZE), (bg_lum, bg_lum, bg_lum, 255))
        d = ImageDraw.Draw(im)
        d.ellipse(
            [CENTRE[0] - radius, CENTRE[1] - radius,
             CENTRE[0] + radius, CENTRE[1] + radius],
            fill=(disc_lum, disc_lum, disc_lum, 255),
        )
    else:
        im = Image.new("RGBA", (SIZE, SIZE), (bg_lum, bg_lum, bg_lum, 0))
        d = ImageDraw.Draw(im)
        d.ellipse(
            [CENTRE[0] - radius, CENTRE[1] - radius,
             CENTRE[0] + radius, CENTRE[1] + radius],
            fill=(disc_lum, disc_lum, disc_lum, 255),
        )
    im.save(path)
    return path


def parse_obj(path):
    """Return (verts Nx3, faces Mx3) with OBJ 1-based indices converted."""
    verts, faces = [], []
    with open(path) as f:
        for line in f:
            p = line.split()
            if not p:
                continue
            if p[0] == "v":
                verts.append([float(p[1]), float(p[2]), float(p[3])])
            elif p[0] == "f":
                faces.append([int(x) - 1 for x in p[1:4]])
    return np.array(verts), np.array(faces)


def verts_to_image_xy(verts, size):
    """OBJ x in [-1,1] -> image col; OBJ z (3rd col) -> image row (flipped)."""
    cols = ((verts[:, 0] + 1) / 2 * (size - 1)).astype(int)
    rows = ((1 - verts[:, 2]) / 2 * (size - 1)).astype(int)
    return np.clip(cols, 0, size - 1), np.clip(rows, 0, size - 1)


def face_disc_fraction(verts, faces, size, radius=RADIUS):
    """Fraction of faces whose centroid falls inside the disc."""
    cols, rows = verts_to_image_xy(verts, size)
    cx = cols[faces].mean(axis=1)
    cy = rows[faces].mean(axis=1)
    dist = np.hypot(cx - CENTRE[0], cy - CENTRE[1])
    return float((dist < radius).mean()), len(faces)


def vert_heights(verts, size, radius=RADIUS):
    """(mean height of verts inside the disc, mean height outside it)."""
    cols, rows = verts_to_image_xy(verts, size)
    dist = np.hypot(cols - CENTRE[0], rows - CENTRE[1])
    inside = dist < radius - 4  # keep clear of the blurred edge
    outside = dist > radius + 4
    return float(verts[inside, 1].mean()), float(verts[outside, 1].mean())


class TestMaskPolarity(unittest.TestCase):
    def test_dark_subject_on_light_background(self):
        gray = np.full((64, 64), 250, dtype=np.float32)
        gray[16:48, 16:48] = 100  # dark square subject, away from the border
        thr = _otsu_threshold(gray)
        mask, height01 = _otsu_subject_mask(gray, thr)
        self.assertEqual(int(mask[32, 32]), 1, "dark subject must be kept")
        self.assertEqual(int(mask[0, 0]), 0, "light background must be dropped")
        self.assertEqual(int(mask[63, 63]), 0)
        self.assertAlmostEqual(float(height01[0, 0]), 0.0, places=5,
                               msg="background height is 0")
        self.assertAlmostEqual(float(height01[32, 32]), 1.0, places=5,
                               msg="most subject-like pixel is height 1")

    def test_light_subject_on_dark_background(self):
        gray = np.full((64, 64), 20, dtype=np.float32)
        gray[16:48, 16:48] = 220  # light square subject
        thr = _otsu_threshold(gray)
        mask, height01 = _otsu_subject_mask(gray, thr)
        self.assertEqual(int(mask[32, 32]), 1, "light subject must be kept")
        self.assertEqual(int(mask[0, 0]), 0, "dark background must be dropped")
        self.assertAlmostEqual(float(height01[0, 0]), 0.0, places=5)
        self.assertAlmostEqual(float(height01[32, 32]), 1.0, places=5)

    def test_subject_touching_frame_falls_back_to_larger_class(self):
        # Subject covers the frame: border is contaminated, so the
        # background must be the larger Otsu class, not the border.
        gray = np.full((64, 64), 100, dtype=np.float32)
        gray[:, :] = 100
        gray[8:56, 8:56] = 230  # light subject fills most of the frame
        thr = _otsu_threshold(gray)
        mask, _ = _otsu_subject_mask(gray, thr)
        self.assertEqual(int(mask[32, 32]), 1, "large light region is the subject")
        self.assertEqual(int(mask[0, 0]), 0, "dark frame is the background")


class TestRunner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runner = DepthInflationRunner()

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, img_path, grid_step=4):
        out = os.path.join(self.tmp.name, "out.obj")
        ok, msg = self.runner.run(img_path, out, grid_step=grid_step, z_scale=0.3)
        self.assertTrue(ok, msg)
        return parse_obj(out)

    def test_dark_disc_on_white_keeps_disc(self):
        img = make_disc(os.path.join(self.tmp.name, "dark.png"), 255, 130)
        verts, faces = self._run(img)
        frac, n = face_disc_fraction(verts, faces, SIZE)
        self.assertGreater(n, 0, "mesh must have faces")
        self.assertGreater(frac, 0.90,
                           f"faces must be on the disc, got {frac:.3f} of {n}")
        h_in, h_out = vert_heights(verts, SIZE)
        self.assertGreater(h_in, h_out,
                           f"disc must be raised above background: {h_in:+.3f} vs {h_out:+.3f}")
        self.assertGreater(float(verts[:, 1].max()), 0.2,
                           "relief must rise near +z_scale")

    def test_light_disc_on_dark_keeps_disc(self):
        img = make_disc(os.path.join(self.tmp.name, "light.png"), 20, 230)
        verts, faces = self._run(img)
        frac, n = face_disc_fraction(verts, faces, SIZE)
        self.assertGreater(n, 0)
        self.assertGreater(frac, 0.90,
                           f"faces must be on the disc, got {frac:.3f} of {n}")
        h_in, h_out = vert_heights(verts, SIZE)
        self.assertGreater(h_in, h_out,
                           f"disc must be raised above background: {h_in:+.3f} vs {h_out:+.3f}")
        self.assertGreater(float(verts[:, 1].max()), 0.2)

    def test_real_example_keeps_disc(self):
        verts, faces = self._run(EXAMPLE_PNG)
        # Ground truth: the disc is the dark side of the Otsu split.
        gray = np.array(ImageOps.grayscale(Image.open(EXAMPLE_PNG).convert("RGBA")))
        thr = _otsu_threshold(gray)
        cols, rows = verts_to_image_xy(verts, SIZE)
        cx = cols[faces].mean(axis=1)
        cy = rows[faces].mean(axis=1)
        on_disc = gray[cy.astype(int), cx.astype(int)] < thr
        frac = float(on_disc.mean())
        self.assertGreater(frac, 0.80,
                           f"faces must be on the disc, got {frac:.3f} of {len(faces)}")
        in_disc = gray[rows, cols] < thr
        h_in = float(verts[in_disc, 1].mean())
        h_out = float(verts[~in_disc, 1].mean())
        self.assertGreater(h_in, h_out,
                           f"disc must be raised: {h_in:+.3f} vs {h_out:+.3f}")
        # The fixed mesh is the subject, not the background sheet, so it
        # has far fewer faces than the inverted 5,696.
        self.assertLess(len(faces), 3000,
                        f"fixed mesh covers the disc only, got {len(faces)} faces")

    def test_solid_image_falls_back_to_full_sheet(self):
        img_path = os.path.join(self.tmp.name, "solid.png")
        Image.new("RGBA", (SIZE, SIZE), (128, 128, 128, 255)).save(img_path)
        verts, faces = self._run(img_path)
        self.assertGreater(len(faces), 5000, "solid image keeps the old full-sheet behaviour")

    def test_transparent_background_keeps_disc(self):
        img = make_disc(os.path.join(self.tmp.name, "alpha.png"), 0, 200, alpha_bg=0)
        verts, faces = self._run(img)
        frac, n = face_disc_fraction(verts, faces, SIZE)
        self.assertGreater(n, 0)
        self.assertGreater(frac, 0.90,
                           f"alpha: faces must be on the disc, got {frac:.3f} of {n}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
