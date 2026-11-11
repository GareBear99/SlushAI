#!/bin/bash
# Monitor generation progress and detect if it stalls

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRIPOSR_OUTPUT="$SCRIPT_DIR/vendors/TripoSR/outputs/triposr_temp"
TIMEOUT_SECONDS=60  # Timeout if no activity for 60 seconds
CHECK_INTERVAL=5    # Check every 5 seconds

last_activity=$(date +%s)
last_vertex_count=0

echo "🔍 Monitoring generation progress..."
echo "   Watching: $TRIPOSR_OUTPUT"
echo "   Timeout: ${TIMEOUT_SECONDS}s of inactivity"
echo ""

while true; do
    current_time=$(date +%s)
    elapsed=$((current_time - last_activity))
    
    # Check if TripoSR is generating
    if [ -d "$TRIPOSR_OUTPUT/0" ]; then
        # Check for mesh.obj
        if [ -f "$TRIPOSR_OUTPUT/0/mesh.obj" ]; then
            vertex_count=$(grep -c "^v " "$TRIPOSR_OUTPUT/0/mesh.obj" 2>/dev/null || echo "0")
            
            if [ "$vertex_count" != "$last_vertex_count" ]; then
                echo "[$(date +%H:%M:%S)] ✓ Progress detected: ${vertex_count} vertices"
                last_activity=$(date +%s)
                last_vertex_count=$vertex_count
                elapsed=0
            fi
        fi
        
        # Check for texture.png
        if [ -f "$TRIPOSR_OUTPUT/0/texture.png" ]; then
            texture_size=$(stat -f%z "$TRIPOSR_OUTPUT/0/texture.png" 2>/dev/null || echo "0")
            if [ "$texture_size" -gt 1000 ]; then
                echo "[$(date +%H:%M:%S)] ✓ Texture being generated: ${texture_size} bytes"
                last_activity=$(date +%s)
                elapsed=0
            fi
        fi
    fi
    
    # Check server logs for progress
    if [ -f "logs/viewer.log" ]; then
        recent_logs=$(tail -5 logs/viewer.log | grep -i "stage\|progress\|completed" | tail -1)
        if [ -n "$recent_logs" ]; then
            echo "[$(date +%H:%M:%S)] Server: ${recent_logs}"
            last_activity=$(date +%s)
            elapsed=0
        fi
    fi
    
    # Check if we've timed out
    if [ $elapsed -gt $TIMEOUT_SECONDS ]; then
        echo ""
        echo "⚠️  No activity detected for ${TIMEOUT_SECONDS} seconds"
        echo "   Last vertex count: ${last_vertex_count}"
        echo ""
        echo "Possible issues:"
        echo "  1. Generation process hung"
        echo "  2. TripoSR backend not responding"
        echo "  3. Missing dependencies"
        echo ""
        echo "Recent server logs:"
        tail -10 logs/viewer.log
        exit 1
    fi
    
    # Show status every check
    echo -ne "\r[$(date +%H:%M:%S)] Activity: ${elapsed}s ago | Vertices: ${last_vertex_count}    "
    
    sleep $CHECK_INTERVAL
done
