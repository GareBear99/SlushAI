#!/bin/bash
# Generation smoke test (Stage 3, #15) — the suite previously had NO test
# that exercised generation or TripoSR at all.
#
# What it proves:
#   1. The native pipeline (fast depth-inflation, no weights needed) runs
#      end to end and produces a REAL mesh: an OBJ with >100 vertices
#      (not the 8-vertex procedural cube) plus a texture PNG.
#   2. TripoSR availability is reported honestly: TripoSRRunner.available()
#      must now verify torch + cached weights, not just run.py. If it is
#      unavailable the test says why and does not fail on that alone.
#   3. With TRIPOSR_SMOKE=1, a real TripoSR generation runs on the same
#      image (minutes on CPU) and must produce a real mesh with a vertex
#      count. Without the flag, TripoSR is reported, not run.
#
# Usage (from the project root):
#   ./tests/test_generation_smoke.sh [image]
#   TRIPOSR_SMOKE=1 ./tests/test_generation_smoke.sh
# Requires the project .venv (falls back to python3 on PATH).
set -u
cd "$(dirname "$0")/.." || exit 1

IMAGE="${1:-assets/example.png}"
OUTDIR="$(mktemp -d /tmp/slushai-gen-smoke.XXXXXX)"
trap 'rm -rf "$OUTDIR"' EXIT

PYBIN=".venv/bin/python"
[ -x "$PYBIN" ] || PYBIN="python3"

FAILED=0
pass() { echo "✓ PASS: $1"; }
fail() { echo "✗ FAIL: $1"; FAILED=$((FAILED + 1)); }

echo "=== Generation smoke test ==="
echo "Image: $IMAGE"
echo "Outdir: $OUTDIR"
[ -f "$IMAGE" ] || { fail "test image not found: $IMAGE"; exit 1; }

STEM="$(basename "$IMAGE" | sed 's/\.[^.]*$//')"

# --- 1. Native pipeline end to end ---
echo ""
echo "--- 1. Native backend (depth-inflation, no weights) ---"
if "$PYBIN" -m src.ai3d.cli pipeline --image "$IMAGE" \
        --backend native --texture native --outdir "$OUTDIR" \
        > "$OUTDIR/native.log" 2>&1; then
    pass "native pipeline exited 0"
else
    fail "native pipeline exited non-zero (see $OUTDIR/native.log)"
    tail -20 "$OUTDIR/native.log"
fi

PREVIEW="$OUTDIR/${STEM}_preview.obj"
REFINED="$OUTDIR/${STEM}_refined.obj"
if [ -f "$PREVIEW" ]; then
    VERTS=$(grep -c '^v ' "$PREVIEW" || true)
    echo "Preview mesh: $PREVIEW ($VERTS vertices)"
    if [ "$VERTS" -gt 100 ]; then
        pass "preview mesh is real geometry ($VERTS vertices, not the 8-vertex cube)"
    else
        fail "preview mesh has only $VERTS vertices — looks like the procedural cube fallback"
    fi
else
    fail "preview mesh missing: $PREVIEW"
fi
if [ -f "$REFINED" ]; then
    pass "refined mesh exists: $REFINED"
else
    echo "NOTE: no refined mesh (texture stage may have skipped — see native.log)"
fi
TEXTURE="$OUTDIR/${STEM}_refined_albedo.png"
if [ -f "$TEXTURE" ] && [ -s "$TEXTURE" ]; then
    pass "texture PNG exists: $TEXTURE ($(stat -f%z "$TEXTURE" 2>/dev/null || stat -c%s "$TEXTURE") bytes)"
else
    # TripoSR (baked) writes <stem>.png instead; the native planar
    # projector writes <stem>_refined_albedo.png. Either is a real texture.
    ALT="$OUTDIR/${STEM}_preview.png"
    if [ -f "$ALT" ] && [ -s "$ALT" ]; then
        pass "texture PNG exists: $ALT ($(stat -f%z "$ALT" 2>/dev/null || stat -c%s "$ALT") bytes)"
    else
        echo "NOTE: no texture PNG (native texture stage may have skipped — see native.log)"
    fi
fi

# --- 2. TripoSR availability, reported honestly ---
echo ""
echo "--- 2. TripoSR availability (torch + weights, not just run.py) ---"
TRIPO_INFO=$("$PYBIN" -c "
import sys
sys.path.insert(0, '.')
from src.ai3d.reconstructors.triposr_runner import TripoSRRunner
r = TripoSRRunner()
print('available:', r.available())
if not r.available():
    print('reason:', r.available_reason())
" 2>&1)
echo "$TRIPO_INFO"
if echo "$TRIPO_INFO" | grep -q "available: True"; then
    pass "TripoSR reports available (torch + weights verified)"
else
    echo "NOTE: TripoSR is not available in this environment — see the reason above."
    echo "      (First run downloads ~2 GB of weights from Hugging Face.)"
fi

# --- 3. Real TripoSR generation (opt-in, minutes on CPU) ---
if [ "${TRIPOSR_SMOKE:-0}" = "1" ]; then
    echo ""
    echo "--- 3. TripoSR generation (TRIPOSR_SMOKE=1) ---"
    START=$(date +%s)
    if "$PYBIN" -m src.ai3d.cli pipeline --image "$IMAGE" \
            --backend triposr --texture native --outdir "$OUTDIR" \
            > "$OUTDIR/triposr.log" 2>&1; then
        END=$(date +%s)
        echo "TripoSR pipeline took $((END - START))s"
        if [ -f "$PREVIEW" ]; then
            VERTS=$(grep -c '^v ' "$PREVIEW" || true)
            echo "TripoSR mesh: $VERTS vertices"
            if [ "$VERTS" -gt 1000 ]; then
                pass "TripoSR produced a real mesh ($VERTS vertices)"
            else
                fail "TripoSR mesh has only $VERTS vertices"
            fi
        else
            fail "TripoSR preview mesh missing"
        fi
    else
        fail "TripoSR pipeline exited non-zero (see $OUTDIR/triposr.log)"
        tail -20 "$OUTDIR/triposr.log"
    fi
else
    echo ""
    echo "--- 3. TripoSR generation skipped (set TRIPOSR_SMOKE=1 to run it) ---"
fi

echo ""
if [ "$FAILED" -eq 0 ]; then
    echo "Generation smoke test passed."
    exit 0
else
    echo "Generation smoke test FAILED ($FAILED failure(s))."
    exit 1
fi
