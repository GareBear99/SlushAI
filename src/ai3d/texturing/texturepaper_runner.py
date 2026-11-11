import subprocess
import sys
from pathlib import Path
from typing import Tuple

class TexturePaperRunner:
    def __init__(self):
        self.root = Path(__file__).resolve().parents[3]
        self.vendor = self.root / 'vendors' / 'TEXTurePaper'

    def available(self) -> bool:
        return self.vendor.exists() and (self.vendor / 'README.md').exists()

    def run(self, mesh_path: str, out_obj: str, prompt: str) -> Tuple[bool, str]:
        if not self.available():
            return False, "TEXTure not installed (run scripts/install_texture.sh)"
        Path(out_obj).parent.mkdir(parents=True, exist_ok=True)
        # TEXTure expects a mesh input and text prompt; outputs textured mesh + textures
        # Many forks expose a CLI like: python run_texture.py --mesh <in> --out <out> --prompt "..."
        # We try a generic runner script name; adapt as needed.
        cmd = [sys.executable, str(self.vendor / 'run_texture.py'), '--mesh', mesh_path, '--out', out_obj]
        if prompt:
            cmd += ['--prompt', prompt]
        try:
            r = subprocess.run(cmd, cwd=str(self.vendor), capture_output=True, text=True, timeout=3600)
            if r.returncode == 0 and Path(out_obj).exists():
                return True, "TEXTure texturing complete"
            else:
                return False, f"TEXTure failed: {r.stderr or r.stdout}"
        except FileNotFoundError:
            return False, "TEXTure entrypoint not found; check vendor repo"
        except Exception as e:
            return False, f"TEXTure error: {e}"
