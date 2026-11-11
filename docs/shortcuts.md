# AI3DModeller Shortcuts & Quick Reference

Quick access guide for all keyboard shortcuts, UI actions, and CLI commands.

## Keyboard Shortcuts

### Viewer Shortcuts
| Shortcut | Action |
|----------|--------|
| `Cmd+S` / `Ctrl+S` | Save screenshot |
| `Escape` | Close lightbox/overlay |
| `Mouse Drag` | Rotate model |
| `Right Mouse Drag` | Pan camera |
| `Mouse Wheel` | Zoom in/out |

## UI Navigation

### Navigation Modes
Click icons in left sidebar:
- 🖼️ **Image** - Upload and generate from images
- 🎲 **Model** - View and manipulate loaded models
- ✨ **Refine** - Refine and add texture
- 🎨 **Texture** - Texture painting tools
- 🏃 **Animate** - Animation (coming soon)

### Image Mode Tabs
- **Image** - Upload image file
- **Prompt** - Text-to-image generation (coming soon)

### View Filters (Right Sidebar)
- 📁 **All** - Show all assets
- 📋 **Images Only** - Show uploaded images
- 🖼 **Models Only** - Show generated models

## Model Controls

### Colors (Theme)
- Theme 1: Purple/Orange
- Theme 2: Blue/Cyan
- Theme 3: Grey Studio
- Theme 4: Red/Black
- Theme 5: Turquoise/Teal
- Theme 6: Green/Pink (Meshy style)

### Quick Colors
- **Extracted** - Color from uploaded image
- **Clay** - Natural clay color
- **White** - Pure white
- **Gray** - Neutral gray
- **Red** - Vibrant red
- **Blue** - Vibrant blue
- **Green** - Vibrant green
- **Black** - Pure black
- **Custom** - Color picker

### Materials
- **Standard** - Default matte material
- **Glossy** - Shiny reflective surface
- **Metal** - Metallic appearance
- **Plastic** - Smooth plastic finish
- **Clay** - Natural clay texture

### Display Modes
- **Solid** - Normal shaded view
- **Wireframe** - Show mesh edges
- **Points** - Show vertices only

### Shading
- **Smooth** - Interpolated normals
- **Flat** - Faceted appearance

## CLI Commands Quick Reference

### Server
```bash
./ai3d.sh start          # Start server
./ai3d.sh start-log      # Start with logging
./ai3d.sh stop           # Stop server
./ai3d.sh restart        # Restart server
./ai3d.sh status         # Check status
```

### Generation
```bash
./ai3d.sh generate <image>    # Generate 3D model
./ai3d.sh load <image>        # Load and auto-generate
./ai3d.sh texture <mesh>      # Add texture to mesh
```

### Models
```bash
./ai3d.sh list           # List all models
./ai3d.sh stats <file>   # Show model statistics
```

### Logs
```bash
./ai3d.sh logs           # Tail logs (real-time)
./ai3d.sh logs-view      # View last 100 entries
./ai3d.sh logs-search <term>  # Search logs
./ai3d.sh logs-clear     # Archive and clear
```

### Screenshots
```bash
./ai3d.sh screenshots    # List all screenshots
```

## Python CLI Commands

### Basic Generation
```bash
python -m src.ai3d.cli pipeline \
  --image input.jpg \
  --backend triposr \
  --texture native \
  --outdir outputs
```

### Load External Image
```bash
python -m src.ai3d.cli load \
  --image photo.jpg \
  --backend triposr \
  --texture native \
  --auto-generate
```

### Reconstruct Only
```bash
python -m src.ai3d.cli reconstruct \
  --image input.jpg \
  --backend triposr \
  --outdir outputs
```

### Texture Only
```bash
python -m src.ai3d.cli texture \
  --mesh model.obj \
  --backend native \
  --outdir outputs
```

## API Endpoints

### Generation
```bash
# Generate 3D model
curl -X POST http://localhost:5000/api/generate \
  -F "image=@photo.jpg" \
  -F "backend=triposr"
```

### Models
```bash
# List models
curl http://localhost:5000/api/models

# Get specific model
curl http://localhost:5000/outputs/model.obj
```

### Screenshots
```bash
# Save screenshot
curl -X POST http://localhost:5000/api/screenshot \
  -H "Content-Type: application/json" \
  -d '{"image":"data:image/png;base64,..."}'
```

### Logging
```bash
# Log action
curl -X POST http://localhost:5000/api/log \
  -H "Content-Type: application/json" \
  -d '{"type":"custom_action","details":{"key":"value"}}'

# Get logs
curl http://localhost:5000/api/logs
curl http://localhost:5000/api/logs?limit=50
```

## File Locations

### Generated Models
```
outputs/
├── temp_image_preview.obj    # Preview model
└── temp_image_refined.obj    # Refined/textured model
```

### Screenshots
```
outputs/screenshots/
└── screenshot_20241126_143022.png
```

### Logs
```
logs/
├── viewer.log                        # Current session
├── archive/viewer_20241126_143022.log
└── sessions/session_20241126_143022.log
```

### Demo Images
```
tests/demo_images/
├── robot.jpg
├── character.png
└── object.jpg
```

## Theme Switching

### Via Header
Click colored dots in header to switch themes instantly

### Via localStorage
```javascript
localStorage.setItem('selected-theme', '6');  // Meshy green/pink
location.reload();
```

### Via Python
```python
# Themes are client-side, no backend config needed
```

## Performance Tips

### Generation
- First TripoSR run downloads ~2GB model
- CPU: 2-3 minutes per model
- GPU: 30-60 seconds per model
- Close memory-intensive apps before generating

### Viewing
- Enable hardware acceleration in browser
- Use Chrome/Firefox for best performance
- Large models (>100k verts) may lag on rotation

### Logging
- Logs auto-rotate on server restart
- Archive logs every 30 days
- Use `./ai3d.sh logs-clear` when logs grow large

## Troubleshooting Quick Fixes

### Server won't start
```bash
./ai3d.sh stop    # Kill any hanging process
./ai3d.sh start   # Restart fresh
```

### Generation stuck
```bash
./ai3d.sh logs    # Check for errors
ps aux | grep python  # Check if process is running
```

### Out of memory
```bash
# Free up memory
./ai3d.sh stop
# Close other apps
./ai3d.sh start
```

### Logs too large
```bash
./ai3d.sh logs-clear  # Archive and reset
```

### Model not loading
```bash
./ai3d.sh list        # Check if model exists
./ai3d.sh stats outputs/model.obj  # Check model integrity
```

## Common Workflows

### Quick Generation
1. Start server: `./ai3d.sh start`
2. Open: http://localhost:5000
3. Drag image onto upload area
4. Click "Generate 3D Model"
5. Wait 2-3 minutes
6. View/manipulate model

### CLI Generation
```bash
./ai3d.sh start
./ai3d.sh generate tests/demo_images/robot.jpg
./ai3d.sh list
```

### Monitoring Generation
```bash
# Terminal 1
./ai3d.sh start-log

# Terminal 2 (while generating)
./ai3d.sh logs
```

### Batch Processing
```bash
for img in tests/demo_images/*.jpg; do
  ./ai3d.sh generate "$img"
done
```

### Export and Share
1. Generate model
2. Press `Cmd+S` or click screenshot button
3. Find screenshot in `outputs/screenshots/`
4. Share screenshot or model file

## Advanced Usage

### Custom Resolution
Currently auto-detected from image. Future: manual override.

### Custom Backend Parameters
Edit `src/ai3d/backends/*.py` for advanced tuning.

### API Integration
See [API Documentation](api.md) for integrating with external services.

### Theme Customization
Edit `viewer/themes.css` to create custom themes.

## Need More Help?

- [Full Documentation](README.md)
- [CLI Commands Reference](cli-commands.md)
- [Logging System](logging.md)
- [Troubleshooting Guide](troubleshooting.md)
