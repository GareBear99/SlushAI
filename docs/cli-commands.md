# AI3DModeller CLI Commands

Complete terminal command reference for all viewer modes and actions.

## Server Management

```bash
# Start viewer server
python viewer/app.py

# Start with logging
python viewer/app.py 2>&1 | tee logs/session_$(date +%Y%m%d_%H%M%S).log

# Stop server
pkill -f "python.*viewer/app.py"

# Restart server
pkill -f "python.*viewer/app.py" && sleep 1 && python viewer/app.py
```

## Image Mode Commands

### Generate 3D Model
```bash
# Basic generation
python -m src.ai3d.cli pipeline \
  --image "path/to/image.jpg" \
  --backend triposr \
  --texture native \
  --outdir outputs

# Fast generation (no texture)
python -m src.ai3d.cli pipeline \
  --image "path/to/image.jpg" \
  --backend triposr \
  --texture none \
  --outdir outputs

# High quality with texture
python -m src.ai3d.cli pipeline \
  --image "path/to/image.jpg" \
  --backend triposr \
  --texture texturepaper \
  --outdir outputs
```

### Load External Image with Presets
```bash
# Load and auto-generate
python -m src.ai3d.cli load \
  --image "path/to/image.jpg" \
  --backend triposr \
  --texture native \
  --auto-generate

# Load without auto-generate
python -m src.ai3d.cli load \
  --image "path/to/image.jpg" \
  --backend triposr \
  --aspect "16:9"
```

## Model Mode Commands

### List Models
```bash
# List all generated models
find outputs -name "*.obj" -type f

# List with details
find outputs -name "*.obj" -type f -exec ls -lh {} \;

# Count vertices in model
grep -c "^v " outputs/model.obj

# Count faces in model
grep -c "^f " outputs/model.obj
```

### Load Model via API
```bash
# Load specific model
curl -X GET "http://localhost:5000/outputs/model_name.obj"

# Get model list
curl -X GET "http://localhost:5000/api/models"
```

## Refine Mode Commands

### Refine Existing Model
```bash
# Add texture to existing model
python -m src.ai3d.cli texture \
  --mesh "outputs/model_preview.obj" \
  --backend native \
  --outdir outputs

# High-quality refinement
python -m src.ai3d.cli texture \
  --mesh "outputs/model_preview.obj" \
  --backend texturepaper \
  --prompt "detailed texture" \
  --outdir outputs
```

## Texture Mode Commands

### Export Model with Custom Material
```bash
# Export OBJ with MTL
# (Currently done through viewer UI)
# Coming soon: CLI export commands
```

## Logging Commands

### View Logs
```bash
# Tail active session log
tail -f logs/viewer.log

# View last 100 lines
tail -100 logs/viewer.log

# Search logs for errors
grep -i "error" logs/*.log

# View generation logs
grep "Generating" logs/*.log
```

### Log Management
```bash
# Archive old logs
mv logs/viewer.log logs/archive/viewer_$(date +%Y%m%d_%H%M%S).log

# Clear old logs (keep last 10)
ls -t logs/*.log | tail -n +11 | xargs rm

# Truncate current log
> logs/viewer.log
```

## Screenshot Commands

### Capture from CLI
```bash
# Via API (requires running server)
curl -X POST "http://localhost:5000/api/screenshot" \
  -o "screenshot_$(date +%Y%m%d_%H%M%S).png"
```

## Asset Management

### Recent Images
```bash
# List recent uploads
ls -lt tests/demo_images/*.{jpg,png,jpeg} | head -10

# Clear recent images cache
rm -rf assets/preloaded/*
```

### Recent Generations
```bash
# List all generated models
ls -lt outputs/*.obj | head -20

# Get model stats
python -c "
import sys
vertices = sum(1 for line in open('outputs/model.obj') if line.startswith('v '))
faces = sum(1 for line in open('outputs/model.obj') if line.startswith('f '))
print(f'Vertices: {vertices:,}, Faces: {faces:,}')
"
```

## Performance Monitoring

### Monitor Generation
```bash
# Watch progress in real-time
watch -n 1 'ls -lh outputs/temp_*.obj 2>/dev/null || echo "No active generation"'

# Monitor memory usage
watch -n 2 'ps aux | grep python | grep -v grep'
```

## Session Management

### Start New Session
```bash
# Create session log
mkdir -p logs/sessions
SESSION_ID=$(date +%Y%m%d_%H%M%S)
echo "Session started: $SESSION_ID" > logs/sessions/$SESSION_ID.log

# Start with session logging
python viewer/app.py 2>&1 | tee logs/sessions/$SESSION_ID.log
```

### End Session
```bash
# Archive session
SESSION_ID=$(date +%Y%m%d_%H%M%S)
tar -czf logs/archive/session_$SESSION_ID.tar.gz logs/*.log outputs/*.obj
```

## Debugging Commands

### Check Server Status
```bash
# Is server running?
ps aux | grep -i "viewer/app.py" | grep -v grep

# Check port
lsof -i :5000

# Test API
curl -s http://localhost:5000/api/models | python -m json.tool
```

### Validate Model
```bash
# Check OBJ file integrity
python -c "
with open('outputs/model.obj') as f:
    lines = f.readlines()
    print(f'Total lines: {len(lines)}')
    print(f'Vertices: {sum(1 for l in lines if l.startswith(\"v \"))}')
    print(f'Faces: {sum(1 for l in lines if l.startswith(\"f \"))}')
    print(f'Normals: {sum(1 for l in lines if l.startswith(\"vn \"))}')
"
```

## Keyboard Shortcuts (in Viewer)

- `Cmd+S` / `Ctrl+S` - Save screenshot
- `Escape` - Close lightbox/overlay
- Mouse drag - Rotate model
- Right mouse drag - Pan camera
- Scroll - Zoom in/out

## Environment Variables

```bash
# Set custom output directory
export AI3D_OUTPUT_DIR="/path/to/outputs"

# Set log level
export AI3D_LOG_LEVEL="DEBUG"

# Set backend preference
export AI3D_DEFAULT_BACKEND="triposr"
```
