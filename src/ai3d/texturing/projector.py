from typing import Tuple
from pathlib import Path
import numpy as np
from PIL import Image

class PlanarProjectorRunner:
    """Native, original texturing: simple planar UV projection from +Z toward -Z.
    Uses input image as the texture; writes OBJ with vt and MTL.
    """

    def run(self, mesh_path: str, out_obj: str, image_for_texture: str) -> Tuple[bool, str]:
        try:
            in_path = Path(mesh_path)
            out_path = Path(out_obj)
            out_path.parent.mkdir(parents=True, exist_ok=True)

            # Read vertices/faces from input OBJ (no vt expected)
            verts = []
            faces = []
            with open(in_path, 'r') as f:
                for line in f:
                    if line.startswith('v '):
                        _, x, y, z = line.strip().split()[:4]
                        verts.append((float(x), float(y), float(z)))
                    elif line.startswith('f '):
                        parts = line.strip().split()[1:]
                        idx = [int(p.split('/')[0]) for p in parts]
                        if len(idx) == 3:
                            faces.append(tuple(idx))
                        elif len(idx) == 4:
                            faces.append((idx[0], idx[1], idx[2]))
                            faces.append((idx[0], idx[2], idx[3]))

            verts = np.array(verts, dtype=np.float32)
            if verts.size == 0 or len(faces) == 0:
                return False, "Input mesh missing verts or faces"

            # Planar projection: map x,z to UV in [0,1]
            xs = verts[:, 0]
            zs = verts[:, 2]
            minx, maxx = xs.min(), xs.max()
            minz, maxz = zs.min(), zs.max()
            spanx = max(1e-6, maxx - minx)
            spanz = max(1e-6, maxz - minz)
            us = (xs - minx) / spanx
            vs = (zs - minz) / spanz

            # Prepare texture file
            tex_img = Image.open(image_for_texture).convert('RGB')
            # Resize to power-of-two-ish for compatibility
            tw, th = tex_img.size
            target = max(256, 2 ** int(np.ceil(np.log2(max(tw, th)))))
            tex_img = tex_img.resize((target, target))
            tex_name = out_path.stem + "_albedo.png"
            tex_path = out_path.parent / tex_name
            tex_img.save(tex_path)

            # Write OBJ with vt and f v/vt
            mtl_name = out_path.stem + ".mtl"
            with open(out_path, 'w') as f:
                f.write("# PlanarProjector textured OBJ\n")
                f.write(f"mtllib {mtl_name}\n")
                for v in verts:
                    f.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
                for u, v in zip(us, vs):
                    f.write(f"vt {u:.6f} {1.0 - v:.6f}\n")
                f.write("usemtl material_0\n")
                for a, b, c in faces:
                    f.write(f"f {a}/{a} {b}/{b} {c}/{c}\n")

            # Write MTL
            with open(out_path.parent / mtl_name, 'w') as f:
                f.write("newmtl material_0\n")
                f.write("Ka 1.000 1.000 1.000\n")
                f.write("Kd 1.000 1.000 1.000\n")
                f.write("Ks 0.000 0.000 0.000\n")
                f.write(f"map_Kd {tex_name}\n")

            return True, "Planar texture projection completed"
        except Exception as e:
            return False, f"PlanarProjector error: {e}"
