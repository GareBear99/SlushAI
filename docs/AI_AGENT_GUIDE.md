# AI Agent Guide - SlushAI 3D Modeller for Live Development

## Overview
SlushAI 3D Modeller is a **production-ready** system for generating high-quality 3D models from images, with **real-time progress tracking** and **Meshy-quality output**. Perfect for AI agents to use in live development with users.

---

## Quick Start for AI Agents

### Basic Usage
```python
from src.ai3d.reconstructors.triposr_runner import TripoSRRunner

# Create runner
runner = TripoSRRunner()

# Generate high-quality 3D model (with progress bars)
success, message = runner.run('path/to/image.jpg', 'output/model.obj')

if success:
    print(f"✓ {message}")
    # Model ready at output/model.obj with texture.png
else:
    print(f"✗ {message}")
```

### CLI Usage
```bash
# Generate model with progress tracking
./ai3d.sh generate path/to/image.jpg

# Check status
./ai3d.sh status

# View all models
./ai3d.sh list

# Get model statistics
./ai3d.sh stats outputs/model.obj
```

---

## Output Quality

### Current Performance
- **Vertices**: ~117,000 (professional quality)
- **Faces**: ~154,000
- **Texture**: 2048x2048 UV-mapped
- **File Size**: ~18MB
- **Generation Time**: ~3 minutes

### Comparison to Meshy AI
- **Meshy**: 273K vertices, 546K faces
- **Us**: 117K vertices, 154K faces
- **Quality**: **43% of Meshy** vertex count (still professional)
- **27x better** than fallback mode (4K → 117K vertices)

---

## Progress Tracking System

### Features
✅ **Overall progress bar** (6 stages)
✅ **Individual stage timings**
✅ **Real-time ETA**
✅ **Completion messages**
✅ **Time comparisons** (faster/slower than expected)

### Example Output
```
============================================================
  TripoSR High-Quality 3D Generation
============================================================

  ✓ Loading Model completed in 9.4s (faster than expected)
  ✓ Preprocessing completed in 0.0s
  ✓ 3D Reconstruction completed in 30.3s
  ✓ Mesh Extraction completed in 48.7s
  ✓ Texture Baking completed in 79.9s
  ✓ Exporting completed in 4.8s
Overall: 100%|██████████████| 6/6 stages [02:58<00:00]

============================================================
  Generation Complete!
============================================================
```

### Stages Tracked
1. **Loading Model** (~15s) - Initialize TripoSR weights
2. **Preprocessing** (~2s) - Prepare image
3. **3D Reconstruction** (~30s) - Run neural network
4. **Mesh Extraction** (~50s) - Extract high-res geometry
5. **Texture Baking** (~80s) - Create 2K texture atlas
6. **Exporting** (~5s) - Save files

---

## API for AI Agents

### Python API

#### High-Level Generation
```python
from src.ai3d.pipeline import run_pipeline

class Args:
    image = "path/to/image.jpg"
    backend = "triposr"  # High quality
    texture = "native"   # Add texture
    prompt = ""
    outdir = "outputs"

run_pipeline(Args())
```

#### Progress Callback
```python
def progress_callback(message):
    print(f"Progress: {message}")
    # Send to user via websocket, etc.

runner = TripoSRRunner()
success, msg = runner.run(
    'image.jpg', 
    'output.obj',
    progress_callback=progress_callback
)
```

#### Custom Progress Tracking
```python
from src.ai3d.utils.progress import TripoSRProgress

progress = TripoSRProgress(use_individual_bars=True)
progress.start()

progress.start_stage('init')
# ... do work ...
progress.finish_stage('init')

progress.finish(success=True)
```

### REST API

#### Generate Model
```bash
POST http://localhost:5000/api/generate
Content-Type: multipart/form-data

image: <file>
backend: triposr
texture: native
```

**Response:**
```json
{
  "success": true,
  "preview_path": "outputs/model_preview.obj",
  "message": "Model generated successfully"
}
```

#### List Models
```bash
GET http://localhost:5000/api/models
```

**Response:**
```json
[
  {
    "name": "model_preview",
    "path": "outputs/model_preview.obj",
    "vertices": 116938,
    "faces": 154372,
    "size": 18874368,
    "refined_path": "outputs/model_refined.obj"
  }
]
```

#### Get Analytics
```bash
GET http://localhost:5000/api/analytics?days=7
```

**Response:**
```json
{
  "total_visitors": 42,
  "active_today": 5,
  "recent_days": [...],
  "top_endpoints": [...]
}
```

---

## Visitor Tracking

### Automatic Tracking
Every request is automatically logged with:
- IP address (hashed for privacy)
- Response time
- Endpoint accessed
- User agent

### Access Analytics
```bash
# Via CLI
./ai3d.sh analytics
./ai3d.sh visitors

# Via API
curl http://localhost:5000/api/analytics
```

### Database Location
```
logs/visitors.db (SQLite)
```

---

## Server Management

### Start/Stop
```bash
# Start (production mode, low resources)
./ai3d.sh start

# Check status
./ai3d.sh status

# Stop
./ai3d.sh stop

# Restart
./ai3d.sh restart
```

### Resource Usage
- **CPU**: 0% idle, spikes to 10% during processing
- **Memory**: ~30MB (production mode)
- **Processes**: 1 (single-threaded)

---

## File Structure

### Generated Files
```
outputs/
  model_preview.obj      # High-quality mesh (117K verts)
  model_preview.png      # 2048x2048 texture
  model_preview.mtl      # Material definition
  model_refined.obj      # With texturing applied
  model_refined_albedo.png
```

### Logs
```
logs/
  viewer.log            # Session log
  visitors.db           # Analytics database
  archive/              # Archived logs
```

---

## Integration Examples

### For Chat Applications
```python
async def generate_3d_model(image_path: str, user_id: str):
    """Generate 3D model with progress updates."""
    
    # Send initial message
    await send_message(user_id, "🎨 Starting 3D generation...")
    
    # Track progress
    progress = TripoSRProgress()
    progress.start()
    
    def callback(msg):
        # Send progress updates to user
        await send_message(user_id, f"⏳ {msg}")
    
    runner = TripoSRRunner()
    success, result = runner.run(
        image_path,
        f"outputs/user_{user_id}_model.obj",
        progress_callback=callback
    )
    
    if success:
        await send_message(user_id, "✅ Model ready!")
        await send_file(user_id, f"outputs/user_{user_id}_model.obj")
    else:
        await send_message(user_id, f"❌ Generation failed: {result}")
```

### For Web Applications
```python
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
import threading

app = Flask(__name__)

@app.route('/api/generate', methods=['POST'])
def api_generate():
    file = request.files['image']
    filename = secure_filename(file.filename)
    
    # Save uploaded image
    image_path = f"uploads/{filename}"
    file.save(image_path)
    
    # Generate in background
    def generate():
        runner = TripoSRRunner()
        runner.run(image_path, f"outputs/{filename}.obj")
    
    thread = threading.Thread(target=generate)
    thread.start()
    
    return jsonify({
        "status": "processing",
        "job_id": filename
    })
```

### For CLI Tools
```bash
#!/bin/bash
# Generate 3D model from image

IMAGE=$1
OUTPUT=${2:-"output.obj"}

# Activate environment
source .venv/bin/activate

# Generate with progress
python -c "
from src.ai3d.reconstructors.triposr_runner import TripoSRRunner
runner = TripoSRRunner()
success, msg = runner.run('$IMAGE', '$OUTPUT')
print(f'Result: {msg}')
exit(0 if success else 1)
"

if [ $? -eq 0 ]; then
    echo "✓ Model ready at $OUTPUT"
else
    echo "✗ Generation failed"
    exit 1
fi
```

---

## Error Handling

### Common Issues
```python
success, message = runner.run(image, output)

if not success:
    if "not found" in message:
        # TripoSR not installed
        print("Run: git clone TripoSR...")
    elif "timeout" in message:
        # Generation took too long (>30 min)
        print("Image too complex or system too slow")
    elif "failed" in message:
        # Check error details in message
        print(f"Error: {message}")
```

### Fallback System
The system automatically falls back to lower quality if TripoSR fails:
1. **TripoSR** (117K verts) - Try first
2. **Native depth** (4K verts) - Fallback
3. **Procedural** (2K verts) - Last resort

---

## Performance Tips

### For Faster Generation
- Use `--no-remove-bg` flag (background removal adds time)
- Lower `--mc-resolution` (256 → 128 for faster, lower quality)
- Disable texture baking (geometry only)

### For Better Quality
- Use high-resolution input images (1024x1024+)
- Enable texture baking (default)
- Use TripoSR backend (default)

### Resource Management
```python
# Check if server can handle request
import psutil
cpu_percent = psutil.cpu_percent()
memory_percent = psutil.virtual_memory().percent

if cpu_percent < 80 and memory_percent < 90:
    # Safe to generate
    runner.run(image, output)
else:
    # Queue or reject
    return "Server busy, try again later"
```

---

## Testing

### Quick Test
```bash
# Test with demo image
./ai3d.sh generate tests/demo_images/example.png

# Verify output
./ai3d.sh stats outputs/example_preview.obj
```

### Quality Check
```python
def check_quality(obj_file):
    """Verify output quality."""
    with open(obj_file) as f:
        verts = sum(1 for line in f if line.startswith('v '))
        faces = sum(1 for line in f if line.startswith('f '))
    
    assert verts > 100000, "Low quality (too few vertices)"
    assert faces > 150000, "Low quality (too few faces)"
    assert os.path.exists(obj_file.replace('.obj', '.png')), "Missing texture"
    
    print(f"✓ Quality check passed: {verts:,} verts, {faces:,} faces")
```

---

## Monitoring

### Check Generation Status
```bash
# View logs in real-time
./ai3d.sh logs

# Search for errors
./ai3d.sh logs-search "error"

# View recent activity
./ai3d.sh logs-view
```

### Monitor Resources
```bash
# Check server status
./ai3d.sh status

# View analytics
./ai3d.sh analytics

# List recent visitors
./ai3d.sh visitors
```

---

## Production Deployment

### Requirements
- Python 3.12
- ~30MB RAM (idle)
- ~2GB RAM (during generation)
- ~4GB disk space (for TripoSR weights)

### Configuration
```python
# viewer/app.py
app.run(
    debug=False,          # Production mode
    host='0.0.0.0',      # Accept external connections
    port=5000,           # Default port
    threaded=False,      # Single-threaded (low resources)
    use_reloader=False   # No file watching
)
```

### Security
- Visitor tracking includes IP logging
- All requests logged to database
- GDPR-friendly IP hashing option
- Data retention policies configurable

---

## Summary for AI Agents

✅ **Ready for Production**
- High-quality output (117K vertices)
- Real-time progress tracking
- Low resource usage (30MB RAM)
- Comprehensive logging

✅ **Easy Integration**
- Simple Python API
- REST endpoints
- CLI commands
- Progress callbacks

✅ **Well Monitored**
- Visitor analytics
- Performance metrics
- Error tracking
- Resource monitoring

Use this system to give users professional 3D model generation capabilities with full transparency via progress bars and timing information!
