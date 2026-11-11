from typing import Tuple
from pathlib import Path

# Very fast fallback: produce a simple cube OBJ if no backend is available
class ProceduralRunner:
    def run(self, image_path: str, out_obj: str) -> Tuple[bool, str]:
        p = Path(out_obj)
        p.parent.mkdir(parents=True, exist_ok=True)
        verts = [
            (-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
            (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)
        ]
        faces = [
            (1,2,3), (1,3,4), (5,6,7), (5,7,8), (1,5,6), (1,6,2),
            (4,8,7), (4,7,3), (1,4,8), (1,8,5), (2,3,7), (2,7,6)
        ]
        with open(p, 'w') as f:
            f.write("# Procedural preview cube\n")
            for v in verts:
                f.write(f"v {v[0]} {v[1]} {v[2]}\n")
            for face in faces:
                f.write(f"f {face[0]} {face[1]} {face[2]}\n")
        return True, "Procedural preview cube created"
