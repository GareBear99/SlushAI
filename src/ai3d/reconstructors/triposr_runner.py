import subprocess
import sys
import shutil
import re
import time
import threading
import os
import multiprocessing
from pathlib import Path
from typing import Tuple, Optional
from ..utils.progress import TripoSRProgress
from ..utils.throttle import CPUThrottler, CPUThrottleConfig

class TripoSRRunner:
    """High-quality TripoSR 3D reconstruction runner.
    
    Uses optimal parameters for professional-quality output:
    - 512 marching cubes resolution for detailed geometry (upgraded from 256)
    - Automatic background removal for clean reconstruction
    - Texture baking at 2048x2048 for high-quality materials
    - Chunked processing to manage memory
    """
    
    def __init__(self, 
                 mc_resolution: int = 512,  # Increased for better 3D detail
                 chunk_size: int = 8192,
                 foreground_ratio: float = 0.85,
                 bake_texture: bool = True,
                 texture_resolution: int = 2048,
                 remove_bg: bool = True,  # Enable background removal
                 cpu_limit_percent: float = 0.80,
                 concurrent_task_factor: float = 1.0):  # 0.5 when 2 tasks, 1.0 when 1 task
        self.root = Path(__file__).resolve().parents[3]  # AI3DModeller/
        self.vendor = self.root / 'vendors' / 'TripoSR'
        
        # High-quality generation parameters
        self.mc_resolution = mc_resolution  # Higher = more detail (512 for pro quality)
        self.chunk_size = chunk_size  # Memory management
        self.foreground_ratio = foreground_ratio  # Object size in frame
        self.bake_texture = bake_texture  # UV-mapped texture vs vertex colors
        self.texture_resolution = texture_resolution  # 2048 for high quality
        self.remove_bg = remove_bg  # Clean input for better reconstruction
        
        # CPU resource management
        self.cpu_limit_percent = cpu_limit_percent  # 0.80 = 80% per core target
        self.concurrent_task_factor = concurrent_task_factor  # Split factor for parallel tasks
        # Use all detected cores for threading
        self.cpu_cores = multiprocessing.cpu_count()
        # When multiple tasks run, split threads equally
        self.max_threads = max(1, int(self.cpu_cores * concurrent_task_factor))

    def _calc_cpulimit_total(self) -> int:
        """Return total CPU limit as a percentage of a single core units.
        Example: 8 cores at 80% each -> 8 * 80 = 640.
        With 2 concurrent tasks: 8 * 80 * 0.5 = 320 per task.
        """
        try:
            return max(80, int(self.cpu_cores * self.cpu_limit_percent * self.concurrent_task_factor * 100))
        except Exception:
            return 160
    
    def available(self) -> bool:
        """Check if TripoSR can actually run: vendor code present, torch
        importable, and the stabilityai/TripoSR weights cached locally
        (config.yaml + model.ckpt under the Hugging Face hub cache, or a
        vendored copy). The old check only looked for run.py, so it
        reported True on a box that could never generate."""
        run_py = self.vendor / 'run.py'
        if not (self.vendor.exists() and run_py.exists()):
            return False
        try:
            import torch  # noqa: F401
        except Exception:
            return False
        # Weights: TSR.from_pretrained('stabilityai/TripoSR') resolves them
        # through the HF hub cache (~/.cache/huggingface/hub, or $HF_HOME).
        try:
            import os
            cache_roots = []
            hf_home = os.environ.get('HF_HOME')
            if hf_home:
                cache_roots.append(Path(hf_home) / 'hub')
            cache_roots.append(Path.home() / '.cache' / 'huggingface' / 'hub')
            for root in cache_roots:
                model_dir = root / 'models--stabilityai--TripoSR'
                if not model_dir.exists():
                    continue
                snapshots = model_dir / 'snapshots'
                if snapshots.exists():
                    for snap in snapshots.glob('*'):
                        if (snap / 'model.ckpt').exists() and (snap / 'config.yaml').exists():
                            return True
                # Blobs layout: a >1 GB blob is the weights file.
                blobs = model_dir / 'blobs'
                if blobs.exists():
                    for blob in blobs.iterdir():
                        if blob.is_file() and blob.stat().st_size > 1_000_000_000:
                            return True
            # Vendored weights (a local copy next to the vendor code).
            if (self.vendor / 'model.ckpt').exists():
                return True
        except Exception:
            return False
        return False

    def available_reason(self) -> str:
        """Human-readable reason when available() is False."""
        run_py = self.vendor / 'run.py'
        if not (self.vendor.exists() and run_py.exists()):
            return 'TripoSR vendor code is missing from vendors/TripoSR'
        try:
            import torch  # noqa: F401
        except Exception:
            return 'torch is not importable in this environment'
        return ('TripoSR weights (stabilityai/TripoSR model.ckpt) are not '
                'cached locally yet — the first run downloads ~2 GB from '
                'Hugging Face')

    def run(self, image_path: str, out_obj: str, progress_callback: Optional[callable] = None) -> Tuple[bool, str]:
        # Run TripoSR reconstruction with high-quality settings.
        # Returns (success, message). Stage 3 fixes vs the old version:
        #  * refuses to start when available() is False (clear reason instead
        #    of a confusing subprocess failure);
        #  * stdout is drained on a thread while the main thread does
        #    process.wait(timeout=1800) — the old code iterated stdout first
        #    and only then waited, so a child that keeps stdout open never
        #    lets the timeout fire and blocks forever; on timeout the child
        #    is killed;
        #  * success requires returncode == 0 AND mesh.obj to exist — the old
        #    code declared success on the mesh file alone, whatever the
        #    exit code was;
        #  * the TripoSR temp dir is always cleaned up (success or failure).
        if not self.available():
            return False, "TripoSR not available: " + self.available_reason()

        # Ensure output directory exists
        out_path = Path(out_obj)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # Create temporary output directory for TripoSR
        temp_out_dir = out_path.parent / 'triposr_temp'
        temp_out_dir.mkdir(exist_ok=True)

        # Convert to absolute paths
        abs_image = str(Path(image_path).resolve())

        # Create progress tracker
        progress = TripoSRProgress()
        progress.start()

        if progress_callback:
            progress_callback("Initializing TripoSR...")

        # Build command with high-quality parameters
        cmd = [
            sys.executable,
            str(self.vendor / 'run.py'),
            abs_image,
            '--output-dir', str(temp_out_dir),
            '--mc-resolution', str(self.mc_resolution),
            '--chunk-size', str(self.chunk_size),
            '--foreground-ratio', str(self.foreground_ratio),
            '--model-save-format', 'obj',
        ]

        # Add background removal flag if disabled (enabled by default in TripoSR)
        if not self.remove_bg:
            cmd.append('--no-remove-bg')

        # Add texture baking if enabled
        if self.bake_texture:
            cmd.extend([
                '--bake-texture',
                '--texture-resolution', str(self.texture_resolution)
            ])

        if progress_callback:
            progress_callback(f"Running TripoSR (resolution: {self.mc_resolution})...")

        try:
            # Set environment variables for CPU thread limiting
            env = os.environ.copy()
            # Use all detected cores for threaded libs
            env['OMP_NUM_THREADS'] = str(self.max_threads)
            env['MKL_NUM_THREADS'] = str(self.max_threads)
            env['NUMEXPR_NUM_THREADS'] = str(self.max_threads)
            env['OPENBLAS_NUM_THREADS'] = str(self.max_threads)
            env['VECLIB_MAXIMUM_THREADS'] = str(self.max_threads)

            print(f"CPU cores detected: {self.cpu_cores}")
            print(f"Thread libraries limited to {self.max_threads} threads")

            # Run TripoSR with real-time output for monitoring
            process = subprocess.Popen(
                cmd,
                cwd=str(self.vendor),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env
            )

            # Start best-effort throttler (80% per core * concurrent factor, ping every 2s)
            throttle = None
            try:
                # Adjust CPU target based on concurrent tasks
                effective_cpu_limit = self.cpu_limit_percent * self.concurrent_task_factor
                throttle = CPUThrottler(process.pid, CPUThrottleConfig(target_fraction=effective_cpu_limit, interval=2.0))
                throttle_thread = threading.Thread(target=throttle.loop, daemon=True)
                throttle_thread.start()
            except Exception as _e:
                # psutil not installed; we already constrained thread counts and priority
                pass

            # Apply total CPU cap via cpulimit if available (optional)
            try:
                cpulimit = shutil.which('cpulimit')
                if cpulimit:
                    total_cap = self._calc_cpulimit_total()  # e.g., 8 cores * 80 = 640
                    print(f"Applying CPU cap with cpulimit: {total_cap}% total")
                    subprocess.Popen([cpulimit, '-p', str(process.pid), '-l', str(total_cap), '-b'])
                else:
                    # Fallback: lower process priority so scheduler backs off under load
                    try:
                        subprocess.run(['renice', '10', '-p', str(process.pid)], check=False)
                        if shutil.which('taskpolicy'):
                            subprocess.run(['taskpolicy', '-b', '-p', str(process.pid)], check=False)
                    except Exception:
                        pass
            except Exception:
                pass

            output_lines = []
            current_stage = None
            stage_timings = {}

            # Background thread to update progress every 500ms
            stop_progress_thread = threading.Event()

            def update_progress_loop():
                while not stop_progress_thread.is_set():
                    if current_stage and progress.stage_start:
                        elapsed = time.time() - progress.stage_start
                        estimate = progress.STAGE_ESTIMATES.get(current_stage, 10)
                        stage_progress = min(0.95, elapsed / estimate)
                        progress.update_stage(current_stage, stage_progress)
                    time.sleep(0.5)

            progress_thread = threading.Thread(target=update_progress_loop, daemon=True)
            progress_thread.start()

            # One line handler: stage tracking + callbacks + output capture.
            def handle_line(raw_line):
                nonlocal current_stage
                line = raw_line.strip()
                if not line:
                    return
                output_lines.append(line)
                if 'Initializing model' in line and '...' in line:
                    progress.start_stage('init')
                    current_stage = 'init'
                elif 'Processing images' in line and '...' in line:
                    if current_stage == 'init':
                        progress.finish_stage('init')
                    progress.start_stage('preprocess')
                    current_stage = 'preprocess'
                elif 'Running model' in line and '...' in line:
                    if current_stage == 'preprocess':
                        progress.finish_stage('preprocess')
                    progress.start_stage('inference')
                    current_stage = 'inference'
                elif 'Extracting mesh' in line and '...' in line:
                    if current_stage == 'inference':
                        progress.finish_stage('inference')
                    progress.start_stage('extract')
                    current_stage = 'extract'
                elif 'Baking texture' in line and '...' in line:
                    if current_stage == 'extract':
                        progress.finish_stage('extract')
                    progress.start_stage('texture')
                    current_stage = 'texture'
                elif 'Exporting' in line and '...' in line:
                    if current_stage == 'texture':
                        progress.finish_stage('texture')
                    progress.start_stage('export')
                    current_stage = 'export'
                elif 'finished in' in line:
                    if current_stage:
                        time_match = re.search(r'finished in ([0-9.]+)ms', line)
                        if time_match:
                            elapsed_ms = float(time_match.group(1))
                            stage_timings[current_stage] = elapsed_ms / 1000.0
                        progress.finish_stage(current_stage)
                        current_stage = None
                if progress_callback:
                    if 'Initializing model' in line:
                        progress_callback("Loading TripoSR model weights...")
                    elif 'Processing images' in line:
                        progress_callback("Preprocessing image...")
                    elif 'Running model' in line:
                        progress_callback("Running 3D reconstruction...")
                    elif 'Extracting mesh' in line:
                        progress_callback("Extracting high-resolution mesh...")
                    elif 'Baking texture' in line:
                        progress_callback("Baking texture atlas...")
                    elif 'Exporting' in line:
                        progress_callback("Finalizing model...")

            # Drain stdout on a thread; the main thread waits with a real
            # timeout and kills a hung child. Lines are consumed from the
            # queue as they arrive so stage progress stays live.
            from collections import deque as _deque
            line_queue = _deque()
            drain_done = threading.Event()

            def drain_stdout():
                try:
                    for raw in process.stdout:
                        line_queue.append(raw)
                except Exception:
                    pass
                finally:
                    drain_done.set()

            drain_thread = threading.Thread(target=drain_stdout, daemon=True)
            drain_thread.start()

            deadline = time.time() + 1800
            timed_out = False
            while True:
                while line_queue:
                    handle_line(line_queue.popleft())
                if process.poll() is not None:
                    break
                if time.time() > deadline:
                    timed_out = True
                    break
                time.sleep(0.05)

            if timed_out:
                try:
                    process.kill()
                except Exception:
                    pass
                try:
                    process.wait(timeout=10)
                except Exception:
                    pass
                try:
                    if throttle:
                        throttle.stop()
                except Exception:
                    pass
                stop_progress_thread.set()
                progress_thread.join(timeout=1.0)
                progress.finish(False)
                return False, "TripoSR timeout (30 minutes exceeded)"

            # Child exited: reap it, then consume any lines still queued.
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                except Exception:
                    pass
                process.wait(timeout=10)
            while line_queue:
                handle_line(line_queue.popleft())
            drain_done.wait(timeout=2)

            # Stop throttler and progress threads
            try:
                if throttle:
                    throttle.stop()
            except Exception:
                pass
            stop_progress_thread.set()
            progress_thread.join(timeout=1.0)

            # Check if generation succeeded: mesh must exist AND the child
            # must have exited 0. A mesh left by a crashed run is not a
            # success.
            generated_mesh = temp_out_dir / '0' / 'mesh.obj'
            generated_texture = temp_out_dir / '0' / 'texture.png'
            returncode = process.returncode

            if returncode == 0 and generated_mesh.exists():
                # Copy the generated mesh to output location
                shutil.copy(generated_mesh, out_obj)

                # Copy texture if it exists
                if self.bake_texture and generated_texture.exists():
                    texture_out = out_path.with_suffix('.png')
                    shutil.copy(generated_texture, texture_out)

                    # Also copy MTL file if it exists
                    mtl_file = generated_mesh.with_suffix('.mtl')
                    if mtl_file.exists():
                        shutil.copy(mtl_file, out_path.with_suffix('.mtl'))

                # Get vertex count for success message
                vertex_count = 0
                try:
                    with open(out_obj, 'r') as f:
                        vertex_count = sum(1 for line in f if line.startswith('v '))
                except Exception:
                    pass

                success_msg = f"TripoSR complete: {vertex_count:,} vertices"
                if self.bake_texture:
                    success_msg += f", {self.texture_resolution}x{self.texture_resolution} texture"

                if progress_callback:
                    progress_callback("Complete!")

                # Ensure last stage is marked complete
                progress.finish(True)
                return True, success_msg
            else:
                error_output = '\n'.join(output_lines[-20:])  # Last 20 lines
                progress.finish(False)
                if returncode != 0:
                    return False, f"TripoSR failed (exit code {returncode}):\n{error_output}"
                return False, f"TripoSR failed:\n{error_output}"

        except subprocess.TimeoutExpired:
            return False, "TripoSR timeout (30 minutes exceeded)"
        except FileNotFoundError:
            return False, f"TripoSR run.py not found at {self.vendor / 'run.py'}"
        except Exception as e:
            return False, f"TripoSR error: {str(e)}"
        finally:
            # Always clean the TripoSR temp dir (Stage 3, #13). The old code
            # kept it "for debugging" on every run, forever.
            try:
                shutil.rmtree(temp_out_dir, ignore_errors=True)
            except Exception:
                pass
