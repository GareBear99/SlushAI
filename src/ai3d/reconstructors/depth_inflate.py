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


class DepthInflationRunner:
    """
    Native, original preview reconstructor.
    Builds a mesh by treating image intensity as height (depth) and triangulating a grid.
    This is a simple, explainable baseline you own entirely.
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
            h = np.array(gray, dtype=np.float32)

            # Normalize heights to [-0.5, 0.5]
            h = (h - h.min()) / max(1e-6, (h.max() - h.min()))
            h = (h - 0.5) * (2 * z_scale)

            # Optional mask from alpha or Otsu
            alpha = np.array(im.split()[-1])
            if alpha.std() < 1e-3:  # no alpha, compute simple Otsu
                thr = _otsu_threshold(np.array(gray))
                mask = (np.array(gray) > thr).astype(np.uint8)
            else:
                mask = (alpha > 8).astype(np.uint8)

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
