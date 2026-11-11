# SlushAI 3D Modeller

**Transform images into 3D models instantly** - A production-ready, local alternative to Meshy AI

[![Status](https://img.shields.io/badge/status-production--ready-green)]() [![License](https://img.shields.io/badge/license-MIT-blue)]() [![Python](https://img.shields.io/badge/python-3.8%2B-blue)]()

---

## 🎯 What Is This?

SlushAI 3D Modeller is a powerful, self-hosted web application that converts images into high-quality 3D models. Think Meshy AI, but running on your own hardware with full control.

### ✨ Key Features

**🎨 Core Capabilities:**
- **Image to 3D**: Upload any image and get a full 3D model in 2-3 minutes
- **High Quality**: 200K+ vertices with TripoSR backend (better than basic "2.5D plaques")
- **Real-time Preview**: Interactive 3D viewer with rotation, zoom, materials
- **Screenshot Gallery**: Save and manage your 3D model screenshots

**👥 User Management:**
- **Google OAuth**: Secure sign-in with Google accounts
- **Badge System**: Progress from Newcomer → Creator → Artist → Master → Legend
- **Weekly Quotas**: Free plan (10/week), Standard (40/week), Pro (120/week)
- **Quick Refills**: $1 adds 10 models instantly (max 10/week)

**⚡ Performance:**
- **Concurrent Processing**: 2-3 workers handle multiple users simultaneously
- **Adaptive Scaling**: Automatically scales up under load (960-1440 models/day capacity)
- **Smart Queue**: Shows position, estimated wait time
- **Maintenance Mode**: Graceful degradation when overloaded

**🔒 Security & Reliability:**
- **Rate Limiting**: 1 request/2s per user on API endpoints
- **Authentication**: Login required for all operations
- **IP Hashing**: GDPR-compliant analytics
- **Session Management**: Secure 30-day sessions

**💳 Monetization Ready:**
- **Subscription Plans**: Free, Standard ($3.47/week), Pro ($7.89/week)
- **Yearly Discounts**: 60% off annual plans
- **One-time Purchases**: $1 refills for emergency boosts
- **Stripe Integration**: Payment processing ready (needs API keys)

---

## 📚 Documentation

**👉 [Complete Documentation Hub](docs/INDEX.md)** - Start here!

The documentation hub has everything explained simply:
- **For Beginners**: Installation, setup, usage guides
- **For Developers**: API reference, architecture, database schema
- **For AI Agents**: Maintenance and modification guides

### Quick Links

| Guide | Purpose | Difficulty |
|-------|---------|------------|
| [docs/INDEX.md](docs/INDEX.md) | **Documentation hub with API reference** | ⭐ All levels |
| [docs/AUTH_SETUP.md](docs/AUTH_SETUP.md) | Google OAuth setup (step-by-step) | ⭐⭐ Beginner |
| [docs/ADVANCED_FEATURES.md](docs/ADVANCED_FEATURES.md) | Badge rewards, rate limiting, maintenance | ⭐⭐⭐⭐ Advanced |
| [docs/CONCURRENT_PROCESSING.md](docs/CONCURRENT_PROCESSING.md) | Task queue and worker scaling | ⭐⭐⭐ Technical |
| [docs/API_USAGE.md](docs/API_USAGE.md) | API endpoints for integrations | ⭐⭐⭐ Developer |

---

## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- 8GB+ RAM recommended
- Google Cloud account (for OAuth - free)

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/AI3DModeller.git
cd AI3DModeller

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install TripoSR backend (recommended)
bash scripts/install_triposr.sh

# 5. Set up Google OAuth (follow docs/AUTH_SETUP.md)
cp .env.example .env
# Edit .env with your Google OAuth credentials

# 6. Run the server
python viewer/app.py

# 7. Open browser
open http://localhost:5000
```

### First Generation

1. Sign in with Google
2. Upload an image
3. Select "TripoSR (High Quality)" backend
4. Click "Generate 3D Model"
5. Wait 2-3 minutes
6. View your 3D model!

---

## 🏗️ Architecture

### Pipeline (Two-Stage)

**Stage 1 - Geometry Generation:**
- Input: Single image
- Process: TripoSR reconstructs 3D geometry
- Output: Base mesh (OBJ/GLB format)
- Quality: 200K+ vertices, full volumetric 3D

**Stage 2 - Refinement (Optional):**
- Input: Base mesh + prompts
- Process: Texture generation/UV mapping
- Output: Textured model with materials

### Backends (Pluggable)

**Geometry:**
- **TripoSR** (Recommended): CPU-friendly, high quality, 2-3 min
- **InstantMesh** (GPU): Fast but requires GPU
- **One-2-3-45** (Classic): Older, stable option
- **Procedural** (Fallback): Quick cube for testing

**Texture:**
- **TEXTure**: Text-guided texture generation
- **Blender**: Projection-based texturing

---

## 💰 Pricing Plans

Visit `/pricing` in the app to see interactive pricing page.

| Plan | Price | Models/Week | Best For |
|------|-------|-------------|----------|
| **Free** | $0 | 10 | Trying the app, casual users |
| **Standard** | $3.47/week or $72/year | 40 | Regular creators, hobbyists |
| **Pro** | $7.89/week or $164/year | 120 | Power users, professionals |
| **Refill** | $1 one-time | +10 models | Emergency boost |

**Yearly savings:** 60% off (Standard saves $108/year, Pro saves $246/year)

---

## 🎮 Usage

### Web Interface

```bash
# Start server
python viewer/app.py

# Visit http://localhost:5000
# Sign in with Google
# Upload image and generate!
```

### CLI (Advanced)

```bash
# Generate with TripoSR
python -m src.ai3d.cli pipeline \
  --image assets/example.jpg \
  --backend triposr \
  --outdir outputs/

# Check output
ls outputs/
# example_preview.obj  # Preview model
# example_refined.obj  # Refined model (if texture enabled)
```

---

## 📊 System Requirements

### Minimum
- **CPU**: 4 cores
- **RAM**: 8GB
- **Storage**: 10GB free
- **OS**: macOS, Linux, Windows (WSL)

### Recommended
- **CPU**: 8+ cores
- **RAM**: 16GB+
- **Storage**: 50GB+ (for model caching)
- **GPU**: Optional (for faster backends)

### Capacity
- **2 workers**: 960 models/day (1-2K users)
- **3 workers**: 1,440 models/day (under heavy load)
- **Rate limit**: 1 API call/2s per user

---

## 🛠️ Tech Stack

**Backend:**
- Python 3.8+
- Flask (web framework)
- Flask-SocketIO (real-time updates)
- Flask-Login (authentication)
- Flask-Limiter (rate limiting)
- SQLite (databases)

**Frontend:**
- Vanilla JavaScript
- Three.js (3D rendering)
- Socket.IO (WebSocket)
- Custom CSS (6 themes)

**AI/ML:**
- TripoSR (geometry generation)
- PyTorch (ML framework)
- PIL/Pillow (image processing)

**Authentication:**
- Google OAuth 2.0
- Authlib (OAuth library)

**Payments (Ready):**
- Stripe integration (needs API keys)

---

## 🎯 Roadmap

### ✅ Completed
- [x] Core 3D generation pipeline
- [x] Web interface with real-time preview
- [x] Google OAuth authentication
- [x] User accounts and quotas
- [x] Badge progression system
- [x] Concurrent processing (2-3 workers)
- [x] Rate limiting
- [x] Maintenance mode
- [x] Pricing page
- [x] Quick refills ($1 add-ons)
- [x] Comprehensive documentation

### 🚧 In Progress
- [ ] Stripe payment integration (needs API keys)
- [ ] Currency conversion (optional)
- [ ] Webhook handling for payments

### 🔮 Future
- [ ] Multi-image input (like Meshy)
- [ ] Animation generation
- [ ] Advanced texture controls
- [ ] GPU acceleration options
- [ ] Export to Unity/Unreal Engine
- [ ] API for external integrations

---

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

See [docs/AI_AGENT_GUIDE.md](docs/AI_AGENT_GUIDE.md) for development guidelines.

---

## 📄 License

MIT License - See LICENSE file for details

---

## 🙏 Acknowledgments

- **TripoSR** by Stability AI and Tripo AI
- **Three.js** for 3D rendering
- **Flask** community
- Inspired by **Meshy AI**

---

## 📞 Support

- **Documentation**: [docs/INDEX.md](docs/INDEX.md)
- **Issues**: GitHub Issues
- **Email**: (Configure in .env)

---

**Made with ❤️ by the SlushAI Team**
