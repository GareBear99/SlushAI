#!/usr/bin/env python
"""Simple inference wrapper for TripoSR without rembg dependency."""
import argparse
import os
import sys
import time
import logging
import numpy as np
import torch
from PIL import Image
from tqdm.auto import tqdm

# Add TripoSR to path
sys.path.insert(0, os.path.dirname(__file__))

# Enable verbose logging for HuggingFace downloads
os.environ['HF_HUB_VERBOSITY'] = 'info'
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger('huggingface_hub').setLevel(logging.INFO)

from tsr.system import TSR

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=str, required=True, help="Input image path")
    parser.add_argument("--out", type=str, required=True, help="Output OBJ path")
    parser.add_argument("--device", default="cpu", type=str, help="Device (cpu/cuda)")
    parser.add_argument("--mc-resolution", default=256, type=int, help="Marching cubes resolution")
    args = parser.parse_args()

    device = args.device
    if device == "cuda" and not torch.cuda.is_available():
        device = "cpu"
    
    print("\n" + "="*60)
    print("TripoSR 3D Reconstruction")
    print("="*60)
    print(f"Device: {device}")
    print(f"Input: {args.image}")
    print(f"Output: {args.out}\n")
    
    # Stage 1: Load model
    print("[1/4] Loading TripoSR model from HuggingFace...")
    print("      (First run will download ~2GB model weights)")
    start_time = time.time()
    
    with tqdm(total=100, desc="      Loading model", unit="%", bar_format='{desc}: {percentage:3.0f}%|{bar}| [{elapsed}<{remaining}]') as pbar:
        pbar.update(10)
        model = TSR.from_pretrained(
            "stabilityai/TripoSR",
            config_name="config.yaml",
            weight_name="model.ckpt",
        )
        pbar.update(70)
        model.to(device)
        pbar.update(20)
    
    load_time = time.time() - start_time
    print(f"      ✓ Model loaded in {load_time:.1f}s\n")

    # Stage 2: Preprocess image
    print("[2/4] Loading and preprocessing image...")
    
    with tqdm(total=100, desc="      Preprocessing", unit="%", bar_format='{desc}: {percentage:3.0f}%|{bar}| [{elapsed}<{remaining}]') as pbar:
        image = Image.open(args.image).convert("RGB")
        pbar.update(40)
        orig_size = image.size
        print(f"      Original size: {orig_size[0]}x{orig_size[1]}")
        
        # Resize to reasonable size if needed
        max_size = 512
        if max(image.size) > max_size:
            ratio = max_size / max(image.size)
            new_size = tuple(int(dim * ratio) for dim in image.size)
            pbar.update(30)
            image = image.resize(new_size, Image.LANCZOS)
            print(f"      Resized to: {new_size[0]}x{new_size[1]}")
            pbar.update(30)
        else:
            pbar.update(60)
    
    print(f"      ✓ Image ready\n")
    
    # Stage 3: Reconstruction
    print("[3/4] Running 3D reconstruction...")
    print("      This may take 1-3 minutes depending on CPU speed")
    start_time = time.time()
    
    with tqdm(total=100, desc="      Reconstructing", unit="%", bar_format='{desc}: {percentage:3.0f}%|{bar}| [{elapsed}<{remaining}]') as pbar:
        pbar.update(5)
        with torch.no_grad():
            scene_codes = model([image], device=device)
        pbar.update(95)
    
    recon_time = time.time() - start_time
    print(f"      ✓ Reconstruction completed in {recon_time:.1f}s\n")
    
    # Stage 4: Extract mesh
    print("[4/4] Extracting mesh geometry...")
    print(f"      Resolution: {args.mc_resolution}^3 voxels")
    start_time = time.time()
    
    with tqdm(total=100, desc="      Extracting mesh", unit="%", bar_format='{desc}: {percentage:3.0f}%|{bar}| [{elapsed}<{remaining}]') as pbar:
        pbar.update(5)
        meshes = model.extract_mesh(scene_codes, has_vertex_color=True, resolution=args.mc_resolution)
        pbar.update(75)
        
        mesh_time = time.time() - start_time
        print(f"      Vertices: {len(meshes[0].vertices):,}, Faces: {len(meshes[0].faces):,}")
        print(f"      ✓ Mesh extracted in {mesh_time:.1f}s")
        
        # Export
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        pbar.update(10)
        meshes[0].export(args.out)
        pbar.update(10)
    
    print("\n" + "="*60)
    print("✅ SUCCESS! 3D model generated")
    print("="*60)
    print(f"Output: {args.out}")
    print(f"Vertices: {len(meshes[0].vertices):,}")
    print(f"Faces: {len(meshes[0].faces):,}")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
