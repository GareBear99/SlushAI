import os
import sys
from pathlib import Path
from typing import Tuple

from .reconstructors.triposr_runner import TripoSRRunner
from .reconstructors.procedural import ProceduralRunner
from .reconstructors.depth_inflate import DepthInflationRunner
from .texturing.texturepaper_runner import TexturePaperRunner
from .texturing.projector import PlanarProjectorRunner


def ensure_outdir(path: str) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def run_reconstruct_only(args):
    outdir = ensure_outdir(args.outdir)
    backend = args.backend

    mesh_path, msg = reconstruct_image(args.image, outdir, backend)
    print(msg)
    print(f"Preview mesh: {mesh_path}")


def run_texture_only(args):
    outdir = ensure_outdir(args.outdir)
    backend = args.backend

    textured_mesh, msg = texture_mesh(args.mesh, outdir, backend, args.prompt, None)
    print(msg)
    print(f"Refined mesh: {textured_mesh}")


def run_pipeline(args):
    outdir = ensure_outdir(args.outdir)

    # Stage 1: geometry
    mesh_path, msg1 = reconstruct_image(args.image, outdir, args.backend)
    print(msg1)

    # Stage 2: texture
    textured_mesh, msg2 = texture_mesh(mesh_path, outdir, args.texture, args.prompt, args.image)
    print(msg2)

    print("Done.\nPreview:", mesh_path, "\nRefined:", textured_mesh)


def reconstruct_image(image_path: str, outdir: Path, backend: str) -> Tuple[str, str]:
    base = Path(image_path).stem
    preview = outdir / f"{base}_preview.obj"

    if backend == "native":
        runner = DepthInflationRunner()
        ok, msg = runner.run(image_path, str(preview))
        if not ok:
            raise RuntimeError(f"Native reconstruction failed: {msg}")
        return str(preview), msg
    elif backend == "triposr":
        runner = TripoSRRunner()
        if not runner.available():
            raise RuntimeError(
                f"TripoSR is not available: {runner.available_reason()}")
        ok, msg = runner.run(image_path, str(preview))
        if ok:
            return str(preview), msg
        # Fall back to the native depth-inflation path (real geometry, and
        # the message says so). The old code fell through to a procedural
        # CUBE after native failed and still reported success — a cube is
        # not a reconstruction, so that fallback is gone: if native fails
        # too, the pipeline fails loudly instead of handing back a cube.
        nat = DepthInflationRunner()
        okn, msgn = nat.run(image_path, str(preview))
        if okn:
            return str(preview), f"{msg} -> Fallback(native): {msgn}"
        raise RuntimeError(
            f"TripoSR failed ({msg}) and the native fallback also failed "
            f"({msgn}) — no model was produced")
    elif backend == "instantmesh":
        # Stage 3 (#13): InstantMesh is not installed and there is no
        # vendor for it. The old code silently substituted a cube and
        # reported success. Refuse with a clear error instead.
        raise RuntimeError(
            "InstantMesh is not installed in this build — the "
            "'instantmesh' backend cannot generate anything. "
            "Use --backend triposr or native.")
    elif backend == "proc":
        # Explicit opt-in only: a procedural cube, labelled as one.
        proc = ProceduralRunner()
        ok, msg = proc.run(image_path, str(preview))
        return str(preview), msg + " (explicit procedural preview cube — not a reconstruction)"
    else:
        raise ValueError(
            f"Unknown geometry backend: {backend!r} "
            "(allowed: native, triposr, instantmesh, proc)")


def texture_mesh(mesh_path: str, outdir: Path, backend: str, prompt: str, source_image: str = None) -> Tuple[str, str]:
    base = Path(mesh_path).stem.replace("_preview", "")
    refined = outdir / f"{base}_refined.obj"

    if backend == "native":
        # Project original image
        src_img = source_image
        if src_img is None:
            # Try to find source image by replacing suffix if present
            cand = Path(mesh_path).with_suffix("")
            for ext in [".png", ".jpg", ".jpeg"]:
                p = Path(str(cand).replace("_preview", ""))
                img = p.with_suffix(ext)
                if img.exists():
                    src_img = str(img)
                    break
        if src_img is None:
            return str(mesh_path), "No source image found for native projection"
        proj = PlanarProjectorRunner()
        ok, msg = proj.run(mesh_path, str(refined), src_img)
        if ok:
            return str(refined), msg
        else:
            return str(mesh_path), "Texture stage skipped: " + msg
    elif backend == "texturepaper":
        # Stage 3 (#13): TEXTurePaper can never work in this build — there
        # is no vendors/TEXTurePaper. Refuse with a clear error instead of
        # pretending the texture stage ran.
        tex = TexturePaperRunner()
        if not tex.available():
            raise RuntimeError(
                "TEXTurePaper is not installed in this build "
                "(vendors/TEXTurePaper is absent) — the 'texturepaper' "
                "texture backend cannot run. Use --texture native or none.")
        ok, msg = tex.run(mesh_path, str(refined), prompt)
        if ok:
            return str(refined), msg
        raise RuntimeError(f"TEXTurePaper failed: {msg}")
    elif backend == "blender":
        # Stage 3 (#13): Blender texture baking is not implemented. Refuse
        # with a clear error instead of silently returning the untextured
        # mesh as if it were refined.
        raise RuntimeError(
            "Blender texture baking is not implemented in this build — "
            "the 'blender' texture backend cannot run. "
            "Use --texture native or none.")
    else:
        return str(mesh_path), "Texture stage disabled"
