# SlushAI 3D Modeller Documentation

SlushAI 3D Modeller is a local image-to-3D generation platform that transforms 2D images into high-quality 3D models using advanced AI backends.

## Quick Links

- [Installation Guide](installation.md)
- [CLI Commands](cli-commands.md) ⭐ NEW
- [Logging System](logging.md) ⭐ NEW
- [CLI Reference](cli-reference.md)
- [Web Viewer Guide](web-viewer.md)
- [API Documentation](api.md)
- [Architecture Overview](architecture.md)
- [Theme System](themes.md)
- [Troubleshooting](troubleshooting.md)

## Features

### 🎨 Web-Based 3D Viewer
- Real-time 3D model preview with Three.js
- Interactive camera controls (orbit, pan, zoom)
- Multiple viewing modes (wireframe, texture, clay)
- Screenshot export functionality
- Asset gallery with generation history

### 🤖 Multiple AI Backends
- **TripoSR** - High-quality 3D reconstruction (Recommended)
- **Native** - Fast 2.5D heightmap generation
- **Procedural** - Fallback geometric shapes

### 🎨 Theme System
- 5 beautiful pre-built themes
- Theme-aware UI components
- Persistent theme preferences
- Smooth transitions

### 🚀 CLI Tools
- Complete terminal control interface (`ai3d.sh`)
- Direct command-line generation
- External image loading with presets
- Server management (start, stop, restart, status)
- Log viewing and analysis
- Model listing and statistics
- Screenshot management
- Batch processing support
- Pipeline orchestration

### 📊 Logging & Monitoring
- Comprehensive action logging
- Automatic session rotation
- JSON-structured log entries
- Real-time log tailing
- Log search and analysis tools
- Performance tracking
- Error monitoring

## Project Structure

```
SlushAI-3D-Modeller/
├── src/ai3d/          # Core Python package
│   ├── cli.py         # Command-line interface
│   ├── pipeline.py    # Generation pipeline
│   └── backends/      # AI backend implementations
├── viewer/            # Web viewer
│   ├── viewer.html    # Main web interface
│   ├── app.py         # Flask backend
│   ├── themes.css     # Theme system styles
│   └── themeSwitcher.js
├── vendors/           # Third-party AI models
│   └── TripoSR/       # TripoSR implementation
├── scripts/           # Utility scripts
├── outputs/           # Generated 3D models
├── assets/            # Static assets
├── tests/             # Test files and demos
│   ├── demo_images/   # Sample input images
│   └── test_files/    # Test resources
├── docs/              # Documentation
└── logs/              # Application logs

```

## Getting Started

### Prerequisites
- Python 3.10+
- pip and virtualenv
- Modern web browser (Chrome, Firefox, Safari)
- 8GB+ RAM (16GB recommended for TripoSR)
- CUDA-compatible GPU (optional, for faster generation)

### Quick Start

1. **Install dependencies:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Start the web viewer:**
   ```bash
   # Simple start
   python viewer/app.py
   
   # Or use the CLI tool
   ./ai3d.sh start
   
   # With session logging
   ./ai3d.sh start-log
   ```

3. **Open in browser:**
   Navigate to http://localhost:5000

4. **Generate your first model:**
   
   **Via Web Interface:**
   - Upload an image via drag-and-drop or click
   - Select TripoSR backend (recommended)
   - Click "Generate 3D Model"
   - View the result in real-time 3D
   
   **Via Terminal:**
   ```bash
   ./ai3d.sh generate tests/demo_images/robot.jpg
   ```

### Terminal Commands

SlushAI 3D Modeller includes a comprehensive CLI tool (`ai3d.sh`) for all operations:

**Server Management:**
```bash
./ai3d.sh start          # Start viewer server
./ai3d.sh stop           # Stop server
./ai3d.sh restart        # Restart server
./ai3d.sh status         # Check server status
```

**Generation:**
```bash
./ai3d.sh generate tests/demo_images/robot.jpg
./ai3d.sh load photo.jpg  # Load and auto-generate
```

**Model Management:**
```bash
./ai3d.sh list           # List all generated models
./ai3d.sh stats model.obj # Show model statistics
```

**Logging:**
```bash
./ai3d.sh logs           # Tail logs in real-time
./ai3d.sh logs-search "error"  # Search logs
./ai3d.sh logs-clear     # Archive and clear
```

**Screenshots:**
```bash
./ai3d.sh screenshots    # List all screenshots
```

See [CLI Commands](cli-commands.md) for complete reference.

### Python API Usage

Direct Python pipeline access:
```bash
python -m src.ai3d.cli pipeline --image input.jpg --backend triposr --texture native
```

Load an external image with preset settings:
```bash
python -m src.ai3d.cli load --image photo.jpg --backend triposr --auto-generate
```

See [CLI Reference](cli-reference.md) for Python API details.

## Key Concepts

### Backends
Backends are the AI engines that generate 3D geometry from 2D images:
- **TripoSR**: Uses a transformer-based model for high-quality full 3D reconstruction
- **Native**: Fast heightmap-based 2.5D extrusion
- **Proc**: Simple procedural fallback shapes

### Texture Refinement
After geometry generation, optional texture/refinement stages add:
- UV mapping
- Color and material information
- Surface details

### Output Formats
- `.obj` - Primary mesh format (vertices and faces)
- Vertex colors embedded in OBJ files
- Material definitions (MTL) for textured models

## Performance Tips

### TripoSR Generation
- First load downloads ~2GB model (one-time)
- Generation takes 2-3 minutes on CPU
- GPU acceleration reduces time to 30-60 seconds
- Close other memory-intensive applications
- Monitor progress with `./ai3d.sh logs`

### Web Viewer
- Modern browsers perform best
- Hardware acceleration recommended
- Large models (>100k vertices) may need decimation
- Use screenshot button or `Cmd+S` / `Ctrl+S` to capture views

### Logging Performance
- Logs are automatically rotated on server restart
- Keep archived logs under 30 days for optimal disk usage
- Use `./ai3d.sh logs-clear` to manually archive logs

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.

## License

See [LICENSE](../LICENSE) file for details.

## Support

For issues, questions, or feature requests:
- Check [Troubleshooting Guide](troubleshooting.md)
- Review [FAQ](faq.md)
- Open an issue on the repository
