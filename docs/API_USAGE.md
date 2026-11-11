# SlushAI 3D Modeller API Usage

## Upload Command (API-Based Generation)

New in this version:
- Real-time browser streaming via Socket.IO (no polling)
- Health endpoint: GET /api/health
- Generate from URL: POST /api/generate_url (JSON)
- Robust success detection that returns the latest preview/refined OBJ path

The `upload` command provides a simple API-like interface for generating 3D models. It's designed for AI agents and automated workflows.

### Usage

```bash
./ai3d.sh upload <image_path> [backend]
```

### Parameters

- `image_path` - Path to the image file (required)
- `backend` - Generation backend (optional, default: `triposr`)

### What It Does

1. **Auto-starts server** - If not running, starts Flask server on port 5000
2. **Opens browser** - Automatically opens http://localhost:5000
3. **Uploads image** - Sends image to `/api/generate` endpoint
4. **Generates server-side** - All processing happens on the server
5. **Returns result** - Shows completion status and model path

### Examples

```bash
# Basic usage
./ai3d.sh upload robot.png

# With specific backend
./ai3d.sh upload robot.png triposr

# From any path
./ai3d.sh upload /path/to/image.jpg
```

### API Flow

```
CLI Command → Server API → TripoSR Backend → Result
     ↓            ↓              ↓              ↓
  Upload      Process        Generate      Return Path
```

### HTTP API Endpoints

- Health check
```bash
curl -s http://localhost:5000/api/health
```

- Generate from file (multipart/form-data)

```bash
curl -X POST http://localhost:5000/api/generate \
  -F "image=@robot.png" \
  -F "backend=triposr"
```

**Response** (200 OK):
```json
{
  "success": true,
  "preview_path": "outputs/robot_preview.obj",
  "message": "Model generated successfully"
}
```

- Generate from URL (JSON)
```bash
curl -s -X POST http://localhost:5000/api/generate_url \
  -H 'Content-Type: application/json' \
  -d '{"image_url": "https://example.com/image.png", "backend": "triposr"}'
```

**Socket.IO events**
- `generation_started` { filename, backend }
- `progress` { stage, percent, elapsed }
- `generation_complete` { preview_path }
- `models_changed` {}

**Response** (500 Error):
```json
{
  "error": "Generation failed",
  "details": "Error message here"
}
```

---

### Comparison: Local vs Server-Side (unchanged behavior; now with streaming)

### Local Generation (`generate`)
```bash
./ai3d.sh generate image.png
```
- Runs Python CLI directly
- Shows progress bars in terminal
- Uses local Python environment
- Best for: Development, testing, debugging

### Server-Side Generation (`upload`)
```bash
./ai3d.sh upload image.png
```
- Uploads to server API
- Processing happens server-side
- Browser auto-opens for viewing
- Best for: Production, AI agents, automation

---

## For AI Agents (Streaming)

The `upload` command is designed to be AI-friendly:

### Simple Integration

```python
import subprocess

# Single command - everything happens automatically
result = subprocess.run(
    ['./ai3d.sh', 'upload', 'image.png'],
    capture_output=True,
    text=True
)

if result.returncode == 0:
    print("✓ Model generated successfully")
    # Model available at server: http://localhost:5000
```

### Direct API Integration (Python + streaming)

```python
import requests

# Start server if needed
subprocess.run(['./ai3d.sh', 'start'])

# Upload image
with open('image.png', 'rb') as f:
    response = requests.post(
        'http://localhost:5000/api/generate',
        files={'image': f},
        data={'backend': 'triposr'}
    )

if response.status_code == 200:
    result = response.json()
print(f"Model: {result['preview_path']}")

# Stream events (optional):
# pip install "python-socketio[client]"
import socketio
sio = socketio.Client()
@sio.on('progress')
def on_progress(data):
    print('progress', data)
sio.connect('http://localhost:5000')
```

---

## Complete Workflow Example

### 1. Test Image Available
```bash
# Your robot warrior image
ls test_inputs/robot.png
```

### 2. Upload and Generate (file or URL)
```bash
./ai3d.sh upload test_inputs/robot.png
# or
./ai3d.sh upload-url https://example.com/robot.png
```

### 3. What Happens
```
Starting viewer server...
✓ Server started at http://localhost:5000

Opening browser viewer...
Uploading and generating 3D model from: robot.png
Backend: triposr
Watch progress in your browser!

[Server processing - 3 minutes]

✓ Generation complete!
Model: outputs/robot_preview.obj
Refresh browser to view the model
```

### 4. View Result
- Browser opens automatically
- Model appears in viewer
- Can rotate, zoom, inspect
- Screenshot and export available

---

## Benefits vs Traditional Methods

| Feature | Traditional | Upload Command |
|---------|------------|----------------|
| Server management | Manual | Automatic |
| Browser opening | Manual | Automatic |
| Progress tracking | Terminal only | Browser + Terminal |
| API-friendly | No | Yes |
| AI agent ready | Complex | Simple |
| Error handling | Manual | Built-in |
| Result viewing | Manual | Auto-refresh |

---

## Error Handling

The command handles common errors automatically:

### Image Not Found
```bash
$ ./ai3d.sh upload missing.png
Error: Image file not found: missing.png
```

### Server Issues
```bash
$ ./ai3d.sh upload image.png
Starting viewer server...
✗ Generation failed (HTTP 500)
Response: {"error": "Details here"}
```

### Generation Timeout
```bash
# Server has 600s (10min) timeout
# Automatically handled in server code
```

---

## Advanced Usage

### Custom Backend (Future)
```bash
# When other backends are available
./ai3d.sh upload image.png stable-diffusion-3d
./ai3d.sh upload image.png custom-backend
```

### Batch Processing
```bash
# Process multiple images
for img in test_inputs/*.png; do
    ./ai3d.sh upload "$img"
    sleep 5  # Wait between generations
done
```

### Integration with Web Apps
```javascript
// Frontend triggers generation
fetch('/api/generate', {
    method: 'POST',
    body: formData
}).then(response => {
    if (response.ok) {
        location.reload();  // Show new model
    }
});
```

---

## Testing

To test the upload command:

```bash
# 1. Save your robot warrior image
cp ~/Downloads/robot.png test_inputs/robot.png

# 2. Run upload command
./ai3d.sh upload test_inputs/robot.png

# 3. Expected output:
# - Server starts (if not running)
# - Browser opens to viewer
# - Image uploads and generates
# - ~3 minutes processing
# - Model appears in browser
```

---

## Summary

The `upload` command provides:
- ✅ One-line API-like interface
- ✅ Automatic server management
- ✅ Browser-based viewing
- ✅ Server-side processing
- ✅ AI agent friendly
- ✅ Error handling built-in
- ✅ Progress tracking ready

Perfect for integrating 3D model generation into any workflow!
