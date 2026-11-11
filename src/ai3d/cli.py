import argparse
import json
import shutil
from pathlib import Path
from .pipeline import run_pipeline, run_reconstruct_only, run_texture_only


def load_external_image(args):
    """Load an external image into the viewer with preset settings."""
    import webbrowser
    import time
    
    # Get project root
    project_root = Path(__file__).parent.parent.parent
    assets_dir = project_root / 'assets' / 'preloaded'
    assets_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy image to assets
    image_path = Path(args.image)
    if not image_path.exists():
        print(f"Error: Image not found: {image_path}")
        return
    
    target_path = assets_dir / f"preload_{image_path.name}"
    shutil.copy2(image_path, target_path)
    
    # Create settings file
    settings = {
        'image': str(target_path.relative_to(project_root)),
        'backend': args.backend,
        'texture': args.texture,
        'aspect': args.aspect,
        'quality': args.quality,
        'auto_generate': args.auto_generate
    }
    
    settings_path = project_root / 'assets' / 'preload_settings.json'
    with open(settings_path, 'w') as f:
        json.dump(settings, f, indent=2)
    
    print(f"\n✅ Image loaded: {image_path.name}")
    print(f"📋 Settings:")
    print(f"   Backend: {args.backend}")
    print(f"   Texture: {args.texture}")
    print(f"   Aspect: {args.aspect}")
    print(f"   Quality: {args.quality}")
    print(f"   Auto-generate: {args.auto_generate}")
    
    if args.auto_generate:
        print(f"\n🚀 Running generation...")
        # Run pipeline directly
        args.outdir = str(project_root / 'outputs')
        args.prompt = ""
        run_pipeline(args)
        print(f"\n✅ Generation complete!")
    
    # Open viewer
    print(f"\n🌐 Opening viewer at http://localhost:5000")
    time.sleep(1)
    webbrowser.open('http://localhost:5000?preload=true')


def main():
    import sys
    p = argparse.ArgumentParser(description="AI3DModeller CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    # pipeline
    sp = sub.add_parser("pipeline", help="Image -> mesh preview -> texture refine")
    sp.add_argument("--image", required=True, help="Input image (jpg/png)")
    sp.add_argument("--prompt", default="", help="Optional text prompt for texture stage")
    sp.add_argument("--outdir", default="outputs", help="Output folder")
    sp.add_argument("--backend", default="native", choices=["native", "triposr", "instantmesh", "proc"], help="Geometry backend")
    sp.add_argument("--texture", default="native", choices=["native", "texturepaper", "blender", "none"], help="Texture backend")

    # reconstruct
    sr = sub.add_parser("reconstruct", help="Image -> mesh preview only")
    sr.add_argument("--image", required=True)
    sr.add_argument("--outdir", default="outputs")
    sr.add_argument("--backend", default="native", choices=["native", "triposr", "instantmesh", "proc"])

    # texture
    st = sub.add_parser("texture", help="Refine/texture an existing mesh")
    st.add_argument("--mesh", required=True)
    st.add_argument("--prompt", default="")
    st.add_argument("--outdir", default="outputs")
    st.add_argument("--backend", default="native", choices=["native", "texturepaper", "blender", "none"])
    
    # load - External image loading with preset settings
    sl = sub.add_parser("load", help="Load external image into viewer with preset settings")
    sl.add_argument("--image", required=True, help="Path to image file")
    sl.add_argument("--backend", default="triposr", choices=["native", "triposr", "instantmesh", "proc"], help="Geometry backend")
    sl.add_argument("--texture", default="native", choices=["native", "texturepaper", "blender", "none"], help="Texture backend")
    sl.add_argument("--aspect", default="1:1", help="Aspect ratio (1:1, 16:9, 9:16, 4:3, 3:4)")
    sl.add_argument("--quality", default="standard", choices=["fast", "standard", "quality"], help="Generation quality/time")
    sl.add_argument("--auto-generate", action="store_true", help="Automatically start generation")

    args = p.parse_args()

    # Stage 3 (#13): the pipeline raises on failure now (no silent cube,
    # no fake success). A failed generation must exit non-zero so the
    # server's subprocess return-code check can see it.
    try:
        if args.cmd == "pipeline":
            run_pipeline(args)
        elif args.cmd == "reconstruct":
            run_reconstruct_only(args)
        elif args.cmd == "texture":
            run_texture_only(args)
        elif args.cmd == "load":
            load_external_image(args)
    except (RuntimeError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
