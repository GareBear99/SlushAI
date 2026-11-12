import math
from typing import Tuple
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps, ImageFilter


def _otsu_threshold(img: np.ndarray) -> float:
    hist, bin_edges = np.histogram(img.flatten(), bins=256, range=(0, 255))
    total = img.size
    sum_total = np.dot(np.arange(256), hist)
    sum_b = 0.0
    w_b = 0
    w_f = 0
    max_var = -1.0
    threshold = 0
    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * hist[t]
        m_b = sum_b / w_b
        m_f = (sum_total - sum_b) / w_f
        var_between = w_b * w_f * (m_b - m_f) ** 2
        if var_between > max_var:
            max_var = var_between
            threshold = t
    return float(threshold)


def _otsu_subject_mask(gray: np.ndarray, thr: float) -> Tuple[np.ndarray, np.ndarray]:
    """Split an opaque image into SUBJECT (mask 1) and BACKGROUND (mask 0).

    The background is the side of the Otsu split that contains the image
    border: the border is background unless the subject touches the frame.
    Height is the distance from the BACKGROUND level, in the subject
    direction, normalised over subject pixels: 0 at the background
    level, 1 at the most subject-like pixel. (Anchoring at the
    background level, not at the split, matters: Otsu lands the split
    ON a flat subject's own grey level, which would flatten the whole
    relief to zero.)

    This works for BOTH polarities, because the polarity is derived from
    the image itself, not assumed:
      - dark subject on a light background: subject = dark side, height
        grows as luminance drops below the background level;
      - light subject on a dark background: subject = bright side, height
        grows as luminance rises above the background level.

    The old code assumed bright = keep/high, which kept the background
    and deleted the subject whenever the subject was the darker side
    (Gary, 2026-11-12: "clearly youv got something inverted and wrong").

    Returns (mask uint8, height01 float32 in [0, 1]).
    """
    bright = gray > thr
    border = np.concatenate([gray[0, :], gray[-1, :], gray[:, 0], gray[:, -1]])
    border_bright_frac = float((border > thr).mean())
    if border_bright_frac > 0.75:
        bg_is_bright = True  # border is (almost) all bright -> background is bright
        bg_level = float(np.median(border))
    elif border_bright_frac < 0.25:
        bg_is_bright = False  # border is (almost) all dark -> background is dark
        bg_level = float(np.median(border))
    else:
        # Subject touches the frame (or no clear border): the background
        # is the larger Otsu class, and its level is that class's mean.
        bg_is_bright = bool(bright.mean() > 0.5)
        bg_level = float(gray[bright].mean()) if bg_is_bright else float(gray[~bright].mean())
    if bg_is_bright:
        mask = (~bright).astype(np.uint8)  # subject = dark side
        dist = np.clip(bg_level - gray, 0, None)  # distance from background
    else:
        mask = bright.astype(np.uint8)  # subject = bright side
        dist = np.clip(gray - bg_level, 0, None)
    if (mask > 0).any():
        peak = float(dist[mask > 0].max())
    else:
        peak = 0.0
    height01 = dist / peak if peak > 1e-6 else np.zeros_like(dist)
    return mask, height01.astype(np.float32)


class DepthInflationRunner:
    """
    Native, original preview reconstructor.
    Builds a mesh by treating image intensity as height (depth) and triangulating a grid.
    This is a simple, explainable baseline you own entirely.

    The mesh is a raised relief OF THE SUBJECT: the subject region is kept
    and lifted, the background region is dropped. Polarity (which side is
    the subject) is derived from the image border, never assumed.
    """

    def run(self, image_path: str, out_obj: str, grid_step: int = 4, z_scale: float = 0.3) -> Tuple[bool, str]:
        try:
            p = Path(out_obj)
            p.parent.mkdir(parents=True, exist_ok=True)

            im = Image.open(image_path).convert("RGBA")
            # Resize if too large to keep mesh reasonable
            max_side = 512
            if max(im.width, im.height) > max_side:
                scale = max_side / float(max(im.width, im.height))
                im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)

            # Height from luminance
            gray = ImageOps.grayscale(im)
            gray = gray.filter(ImageFilter.GaussianBlur(radius=1.0))
            g = np.array(gray, dtype=np.float32)

            # Subject mask + height, polarity derived from the image.
            alpha = np.array(im.split()[-1])
            if alpha.std() < 1e-3:  # no alpha: Otsu split, background anchored to the border
                thr = _otsu_threshold(g)
                mask, height01 = _otsu_subject_mask(g, thr)
                if mask.mean() < 0.01:
                    # No detectable subject (solid / gradient image): fall
                    # back to the whole image as the subject, as before.
                    mask = np.ones_like(mask)
                    lo = g.min()
                    hi = g.max()
                    height01 = (g - lo) / max(1e-6, hi - lo)
            else:
                # Transparency defines the subject directly.
                mask = (alpha > 8).astype(np.uint8)
                opaque = mask > 0
                height01 = np.zeros_like(g)
                if opaque.any():
                    # Normalise within the opaque region only, so the
                    # transparent (black) pixels cannot skew the relief.
                    lo = g[opaque].min()
                    hi = g[opaque].max()
                    height01[opaque] = (g[opaque] - lo) / max(1e-6, hi - lo)

            # Heights in [-z_scale, +z_scale]: background at the base plane,
            # most subject-like pixel at the top of the relief.
            h = (height01 - 0.5) * (2 * z_scale)

            H, W = h.shape
            xs = np.arange(0, W, grid_step, dtype=np.int32)
            ys = np.arange(0, H, grid_step, dtype=np.int32)
            # ensure last index included
            if xs[-1] != W - 1:
                xs = np.append(xs, W - 1)
            if ys[-1] != H - 1:
                ys = np.append(ys, H - 1)

            # Map to [-1,1] in x,y preserving aspect
            ax = 2.0 / max(1, W - 1)
            ay = 2.0 / max(1, H - 1)
            xgrid, ygrid = np.meshgrid(xs, ys)
            X = (xgrid * ax - 1.0).astype(np.float32)
            Y = (1.0 - ygrid * ay).astype(np.float32)  # flip y so up is positive
            Z = h[ygrid, xgrid]

            # Vertex list
            verts = np.stack([X, Z, Y], axis=-1).reshape(-1, 3)  # (ny*nx, 3)

            # Faces (two tris per cell), with simple mask check (skip if corner pixels mostly background)
            nx = xs.shape[0]
            ny = ys.shape[0]
            faces = []
            for j in range(ny - 1):
                for i in range(nx - 1):
                    # indices in flattened grid
                    v00 = j * nx + i
                    v10 = j * nx + (i + 1)
                    v01 = (j + 1) * nx + i
                    v11 = (j + 1) * nx + (i + 1)
                    # mask vote
                    m = mask[ys[j]:ys[j+1]+1, xs[i]:xs[i+1]+1]
                    if m.size == 0:
                        keep = True
                    else:
                        keep = (m.mean() > 0.35)
                    if keep:
                        faces.append((v00 + 1, v10 + 1, v11 + 1))
                        faces.append((v00 + 1, v11 + 1, v01 + 1))

            # Write OBJ (no UV; preview geometry only)
            with open(p, 'w') as f:
                f.write("# DepthInflation preview OBJ\n")
                f.write(f"# Image: {Path(image_path).name}\n")
                f.write(f"# Vertices: {len(verts)} Faces: {len(faces)}\n")
                for v in verts:
                    f.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
                for a, b, c in faces:
                    f.write(f"f {a} {b} {c}\n")

            return True, f"DepthInflation preview created ({len(verts)} verts, {len(faces)} faces)"
        except Exception as e:
            return False, f"DepthInflation error: {e}"
