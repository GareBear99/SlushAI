#!/bin/bash
# AI3DModeller Terminal Control Script
# Complete terminal interface for all viewer actions

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Display banner
banner() {
    echo -e "${PURPLE}╔═══════════════════════════════════════╗${NC}"
    echo -e "${PURPLE}║${NC}     ${CYAN}🎨 AI3DModeller CLI${NC}           ${PURPLE}║${NC}"
    echo -e "${PURPLE}╚═══════════════════════════════════════╝${NC}"
    echo ""
}

# Show usage
usage() {
    banner
    echo -e "${CYAN}Usage:${NC} ./ai3d.sh <command> [options]"
    echo ""
    echo -e "${YELLOW}Server Commands:${NC}"
    echo "  start               Start the viewer server"
    echo "  start-log          Start server with session logging"
    echo "  stop               Stop the viewer server"
    echo "  restart            Restart the viewer server"
    echo "  status             Check server status"
    echo ""
    echo -e "${YELLOW}Generation Commands:${NC}"
    echo "  generate <image>   Generate 3D model from image (local)"
    echo "  upload <image>     Upload image to server and generate"
    echo "  upload-url <url>   Generate from an image URL (server fetches it)"
    echo "  load <image>       Load image and auto-generate"
    echo "  texture <mesh>     Add texture to existing mesh"
    echo ""
    echo -e "${YELLOW}Model Commands:${NC}"
    echo "  list               List all generated models"
    echo "  stats <file>       Show model statistics"
    echo ""
    echo -e "${YELLOW}Log Commands:${NC}"
    echo "  logs               Tail active log file"
    echo "  logs-view          View last 100 log entries"
    echo "  logs-search <term> Search logs for term"
    echo "  logs-clear         Archive and clear logs"
    echo ""
    echo -e "${YELLOW}Screenshot Commands:${NC}"
    echo "  screenshot         Capture screenshot (requires running server)"
    echo "  screenshots        List all screenshots"
    echo ""
    echo -e "${YELLOW}Analytics Commands:${NC}"
    echo "  analytics          View visitor statistics"
    echo "  visitors           List all visitors"
    echo "  visitor-info <ip>  Get specific visitor history"
    echo ""
    echo -e "${YELLOW}Examples:${NC}"
    echo "  ./ai3d.sh start"
    echo "  ./ai3d.sh generate tests/demo_images/robot.jpg"
    echo "  ./ai3d.sh list"
    echo "  ./ai3d.sh logs"
    echo ""
}

# Check if server is running
is_running() {
    pgrep -f "python.*viewer/app.py" > /dev/null
}

# Wait for server to be ready
wait_for_server() {
    local retries=30
    local url="http://localhost:5000/api/health"
    for i in $(seq 1 $retries); do
        code=$(curl -s -o /dev/null -w "%{http_code}" "$url" || echo 000)
        if [ "$code" = "200" ]; then
            return 0
        fi
        sleep 0.5
    done
    return 1
}

# Start server
start_server() {
    if is_running; then
        echo -e "${YELLOW}Server is already running${NC}"
        return 1
    fi
    
    echo -e "${GREEN}Starting AI3DModeller server...${NC}"
    python viewer/app.py &
    # Wait for health endpoint
    if wait_for_server; then
        :
    else
        echo -e "${RED}✗ Server did not respond to health check${NC}"
        return 1
    fi
    
    if is_running; then
        echo -e "${GREEN}✓ Server started at http://localhost:5000${NC}"
    else
        echo -e "${RED}✗ Failed to start server${NC}"
        return 1
    fi
}

# Start server with logging
start_server_log() {
    if is_running; then
        echo -e "${YELLOW}Server is already running${NC}"
        return 1
    fi
    
    mkdir -p logs/sessions
    SESSION_ID=$(date +%Y%m%d_%H%M%S)
    echo -e "${GREEN}Starting AI3DModeller server with session logging...${NC}"
    echo -e "${CYAN}Session ID: ${SESSION_ID}${NC}"
    
    python viewer/app.py 2>&1 | tee "logs/sessions/session_${SESSION_ID}.log" &
    sleep 2
    
    if is_running; then
        echo -e "${GREEN}✓ Server started at http://localhost:5000${NC}"
        echo -e "${CYAN}Log file: logs/sessions/session_${SESSION_ID}.log${NC}"
    else
        echo -e "${RED}✗ Failed to start server${NC}"
        return 1
    fi
}

# Stop server
stop_server() {
    if ! is_running; then
        echo -e "${YELLOW}Server is not running${NC}"
        return 1
    fi
    
    echo -e "${YELLOW}Stopping server...${NC}"
    pkill -f "python.*viewer/app.py"
    sleep 1
    
    if ! is_running; then
        echo -e "${GREEN}✓ Server stopped${NC}"
    else
        echo -e "${RED}✗ Failed to stop server${NC}"
        return 1
    fi
}

# Check server status
check_status() {
    if is_running; then
        PID=$(pgrep -f "python.*viewer/app.py")
        echo -e "${GREEN}✓ Server is running (PID: ${PID})${NC}"
        echo -e "${CYAN}URL: http://localhost:5000${NC}"
        
        # Check if port is open
        if lsof -i :5000 > /dev/null 2>&1; then
            echo -e "${GREEN}✓ Port 5000 is open${NC}"
        fi
    else
        echo -e "${RED}✗ Server is not running${NC}"
    fi
}

# Generate 3D model with browser viewer
generate_model() {
    local image="$1"
    
    if [ -z "$image" ]; then
        echo -e "${RED}Error: No image specified${NC}"
        echo "Usage: ./ai3d.sh generate <image>"
        return 1
    fi
    
    if [ ! -f "$image" ]; then
        echo -e "${RED}Error: Image file not found: ${image}${NC}"
        return 1
    fi
    
    # Start server if not running
    if ! is_running; then
        echo -e "${CYAN}Starting viewer server...${NC}"
        start_server
        sleep 2
    fi
    
    # Open browser to viewer
    echo -e "${CYAN}Opening browser viewer...${NC}"
    open "http://localhost:5000"
    sleep 1
    
    echo -e "${GREEN}Generating 3D model from: ${image}${NC}"
    echo -e "${CYAN}Watch progress in your browser!${NC}"
    echo ""
    
    python -m src.ai3d.cli pipeline \
        --image "$image" \
        --backend triposr \
        --texture native \
        --outdir outputs
    
    # Refresh browser to show result
    echo ""
    echo -e "${GREEN}✓ Generation complete! Refresh browser to view model.${NC}"
}

# Upload image to server and generate (API-based)
upload_and_generate() {
    local image="$1"
    local backend="${2:-triposr}"
    
    if [ -z "$image" ]; then
        echo -e "${RED}Error: No image specified${NC}"
        echo "Usage: ./ai3d.sh upload <image> [backend]"
        return 1
    fi
    
    if [ ! -f "$image" ]; then
        echo -e "${RED}Error: Image file not found: ${image}${NC}"
        return 1
    fi
    
    # Start server if not running
    if ! is_running; then
        echo -e "${CYAN}Starting viewer server...${NC}"
        start_server
        sleep 3
    fi
    
    # Ensure server healthy and open browser to viewer (image mode)
    echo -e "${CYAN}Opening browser viewer...${NC}"
    if ! wait_for_server; then
        echo -e "${RED}✗ Server not healthy${NC}"
        return 1
    fi
    open "http://localhost:5000/?mode=image"
    # Give the UI time to boot before upload
    sleep 3
    
    echo -e "${GREEN}Uploading and generating 3D model from: $(basename "$image")${NC}"
    echo -e "${CYAN}Backend: ${backend}${NC}"
    echo -e "${CYAN}Image size: $(ls -lh "$image" | awk '{print $5}')${NC}"
    echo -e "${YELLOW}Watch progress in your browser!${NC}"
    echo -e "${YELLOW}Server logs: tail -f logs/viewer.log${NC}"
    echo ""
    
    # Upload to server API (with progress monitoring in background)
    echo -e "${CYAN}Uploading to server...${NC}"
    
    # Start progress monitor in background
    (
        sleep 10  # Wait for generation to start
        triposr_out="vendors/TripoSR/outputs/triposr_temp/0"
        last_count=0
        stall_time=0
        
        while true; do
            if [ -f "$triposr_out/mesh.obj" ]; then
                count=$(grep -c "^v " "$triposr_out/mesh.obj" 2>/dev/null || echo "0")
                if [ "$count" -gt "$last_count" ]; then
                    echo -e "\n${GREEN}↻ Generating: ${count} vertices${NC}"
                    last_count=$count
                    stall_time=0
                else
                    stall_time=$((stall_time + 5))
                    if [ $stall_time -gt 60 ]; then
                        echo -e "\n${YELLOW}⚠️  Generation stalled at ${last_count} vertices${NC}"
                        break
                    fi
                fi
            fi
            sleep 5
        done
    ) &
    monitor_pid=$!
    
    # Upload and wait for response
    response=$(curl -s -X POST http://localhost:5000/api/generate \
        -F "image=@${image}" \
        -F "backend=${backend}" \
        -w "\n%{http_code}")
    
    # Kill monitor
    kill $monitor_pid 2>/dev/null
    
    http_code=$(echo "$response" | tail -n1)
    body=$(printf "%s" "$response" | sed '$d')
    
    if [ "$http_code" = "200" ]; then
        echo -e "${GREEN}✓ Generation complete!${NC}"
        
        # Try to extract path from JSON
        if command -v python3 &> /dev/null; then
            preview_path=$(echo "$body" | python3 -c "import sys, json; print(json.load(sys.stdin).get('preview_path', ''))" 2>/dev/null)
            if [ -n "$preview_path" ]; then
                echo -e "${CYAN}Model: ${preview_path}${NC}"
            fi
        fi
        
        echo -e "${YELLOW}Refresh browser to view the model${NC}"
    else
        echo -e "${RED}✗ Generation failed (HTTP ${http_code})${NC}"
        echo -e "${YELLOW}Response: ${body}${NC}"
        return 1
    fi
}

# List models
list_models() {
    echo -e "${CYAN}Generated Models:${NC}"
    echo ""
    
    if [ ! -d "outputs" ]; then
        echo -e "${YELLOW}No outputs directory found${NC}"
        return 0
    fi
    
    local count=0
    while IFS= read -r -d '' file; do
        count=$((count + 1))
        local name=$(basename "$file")
        local size=$(ls -lh "$file" | awk '{print $5}')
        local date=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M" "$file" 2>/dev/null || stat -c "%y" "$file" | cut -d'.' -f1)
        
        echo -e "${GREEN}[$count]${NC} ${name}"
        echo -e "    Size: ${size}  Modified: ${date}"
        
        # Get vertex/face count
        local verts=$(grep -c "^v " "$file" 2>/dev/null || echo "0")
        local faces=$(grep -c "^f " "$file" 2>/dev/null || echo "0")
        echo -e "    Vertices: ${verts}  Faces: ${faces}"
        echo ""
    done < <(find outputs -name "*.obj" -type f -not -name "*_refined*" -print0 | sort -z)
    
    if [ $count -eq 0 ]; then
        echo -e "${YELLOW}No models found${NC}"
    fi
}

# Show model stats
model_stats() {
    local file="$1"
    
    if [ -z "$file" ]; then
        echo -e "${RED}Error: No model file specified${NC}"
        return 1
    fi
    
    if [ ! -f "$file" ]; then
        echo -e "${RED}Error: Model file not found: ${file}${NC}"
        return 1
    fi
    
    echo -e "${CYAN}Model Statistics: $(basename "$file")${NC}"
    echo ""
    
    local size=$(ls -lh "$file" | awk '{print $5}')
    local verts=$(grep -c "^v " "$file")
    local normals=$(grep -c "^vn " "$file")
    local texcoords=$(grep -c "^vt " "$file")
    local faces=$(grep -c "^f " "$file")
    
    echo -e "${GREEN}File Size:${NC}      $size"
    echo -e "${GREEN}Vertices:${NC}       $verts"
    echo -e "${GREEN}Normals:${NC}        $normals"
    echo -e "${GREEN}Tex Coords:${NC}     $texcoords"
    echo -e "${GREEN}Faces:${NC}          $faces"
}

# View logs
view_logs() {
    if [ ! -f "logs/viewer.log" ]; then
        echo -e "${YELLOW}No log file found${NC}"
        return 1
    fi
    
    echo -e "${CYAN}Tailing logs (Ctrl+C to exit)...${NC}"
    tail -f logs/viewer.log
}

# View last 100 log entries
view_logs_recent() {
    if [ ! -f "logs/viewer.log" ]; then
        echo -e "${YELLOW}No log file found${NC}"
        return 1
    fi
    
    echo -e "${CYAN}Last 100 log entries:${NC}"
    tail -100 logs/viewer.log
}

# Search logs
search_logs() {
    local term="$1"
    
    if [ -z "$term" ]; then
        echo -e "${RED}Error: No search term specified${NC}"
        return 1
    fi
    
    if [ ! -f "logs/viewer.log" ]; then
        echo -e "${YELLOW}No log file found${NC}"
        return 1
    fi
    
    echo -e "${CYAN}Searching logs for: ${term}${NC}"
    grep -i "$term" logs/viewer.log || echo -e "${YELLOW}No matches found${NC}"
}

# Clear logs
clear_logs() {
    if [ ! -f "logs/viewer.log" ]; then
        echo -e "${YELLOW}No log file found${NC}"
        return 0
    fi
    
    echo -e "${YELLOW}Archiving and clearing logs...${NC}"
    mkdir -p logs/archive
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    mv logs/viewer.log "logs/archive/viewer_${TIMESTAMP}.log"
    echo -e "${GREEN}✓ Logs archived to logs/archive/viewer_${TIMESTAMP}.log${NC}"
}

# Capture screenshot
capture_screenshot() {
    if ! is_running; then
        echo -e "${RED}Error: Server is not running${NC}"
        echo -e "${YELLOW}Start the server first: ./ai3d.sh start${NC}"
        return 1
    fi
    
    echo -e "${CYAN}Capturing screenshot...${NC}"
    
    # Try to capture screenshot using AppleScript (macOS)
    if command -v osascript &> /dev/null; then
        # Open browser to the viewer
        osascript -e 'tell application "Safari" to activate' 2>/dev/null || \
        osascript -e 'tell application "Google Chrome" to activate' 2>/dev/null || \
        osascript -e 'tell application "Firefox" to activate' 2>/dev/null
        
        echo -e "${GREEN}Please use the Screenshot button in the viewer UI${NC}"
        echo -e "${CYAN}Or press the Screenshot button in the web interface${NC}"
        echo -e "${YELLOW}Screenshots will be saved to: outputs/screenshots/${NC}"
    else
        echo -e "${YELLOW}Screenshot feature requires the web viewer UI${NC}"
        echo -e "${CYAN}Open http://localhost:5000 and click the Screenshot button${NC}"
    fi
}

# View analytics
view_analytics() {
    if ! is_running; then
        echo -e "${YELLOW}Server is not running${NC}"
        echo -e "${CYAN}Analytics are available when server is running${NC}"
        return 1
    fi
    
    echo -e "${CYAN}Visitor Analytics:${NC}"
    echo ""
    curl -s http://localhost:5000/api/analytics | python -m json.tool
}

# List visitors
list_visitors() {
    DB_PATH="logs/visitors.db"
    
    if [ ! -f "$DB_PATH" ]; then
        echo -e "${YELLOW}No visitor database found${NC}"
        return 0
    fi
    
    echo -e "${CYAN}Recent Visitors:${NC}"
    echo ""
    
    sqlite3 "$DB_PATH" <<EOF
.mode column
.headers on
SELECT 
    ip_address,
    visit_count,
    datetime(first_seen) as first_visit,
    datetime(last_seen) as last_visit
FROM visitors
ORDER BY last_seen DESC
LIMIT 20;
EOF
}

# Get visitor info
visitor_info() {
    local ip="$1"
    
    if [ -z "$ip" ]; then
        echo -e "${RED}Error: No IP address specified${NC}"
        echo "Usage: ./ai3d.sh visitor-info <ip_address>"
        return 1
    fi
    
    if ! is_running; then
        echo -e "${YELLOW}Server is not running${NC}"
        return 1
    fi
    
    echo -e "${CYAN}Visitor History for ${ip}:${NC}"
    echo ""
    
    # This would need the visitor's actual request, simulating with current
    curl -s "http://localhost:5000/api/visitor/history" | python -m json.tool
}

# List screenshots
list_screenshots() {
    echo -e "${CYAN}Screenshots:${NC}"
    echo ""
    
    if [ ! -d "outputs/screenshots" ]; then
        echo -e "${YELLOW}No screenshots directory found${NC}"
        return 0
    fi
    
    local count=0
    while IFS= read -r -d '' file; do
        count=$((count + 1))
        local name=$(basename "$file")
        local size=$(ls -lh "$file" | awk '{print $5}')
        local date=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M" "$file" 2>/dev/null || stat -c "%y" "$file" | cut -d'.' -f1)
        
        echo -e "${GREEN}[$count]${NC} ${name}"
        echo -e "    Size: ${size}  Date: ${date}"
    done < <(find outputs/screenshots -name "*.png" -type f -print0 | sort -zr)
    
    if [ $count -eq 0 ]; then
        echo -e "${YELLOW}No screenshots found${NC}"
    fi
}

# Upload from URL
upload_and_generate_url() {
    local url="$1"
    local backend="${2:-triposr}"
    if [ -z "$url" ]; then
        echo -e "${RED}Error: No image URL provided${NC}"
        echo "Usage: ./ai3d.sh upload-url <image_url> [backend]"
        return 1
    fi
    if ! is_running; then
        start_server || return 1
        sleep 2
    fi
    open "http://localhost:5000/?mode=image"
    sleep 2
    echo -e "${CYAN}Requesting server to generate from URL...${NC}"
    resp=$(curl -s -X POST http://localhost:5000/api/generate_url \
        -H 'Content-Type: application/json' \
        -d "{\"image_url\": \"$url\", \"backend\": \"$backend\"}" \
        -w "\n%{http_code}")
    code=$(echo "$resp" | tail -n1)
    body=$(printf "%s" "$resp" | sed '$d')
    if [ "$code" = "200" ]; then
        echo -e "${GREEN}✓ Server accepted URL. Watch the browser for live progress.${NC}"
    else
        echo -e "${RED}✗ Request failed (HTTP ${code})${NC}"
        echo -e "${YELLOW}${body}${NC}"
        return 1
    fi
}

# Main command router
case "${1:-}" in
    start)
        start_server
        ;;
    start-log)
        start_server_log
        ;;
    stop)
        stop_server
        ;;
    restart)
        stop_server
        sleep 1
        start_server
        ;;
    status)
        check_status
        ;;
    generate)
        generate_model "$2"
        ;;
    upload)
        upload_and_generate "$2" "$3"
        ;;
    upload-url)
        upload_and_generate_url "$2" "$3"
        ;;
    load)
        python -m src.ai3d.cli load --image "$2" --backend triposr --texture native --auto-generate
        ;;
    texture)
        python -m src.ai3d.cli texture --mesh "$2" --backend native --outdir outputs
        ;;
    list)
        list_models
        ;;
    stats)
        model_stats "$2"
        ;;
    logs)
        view_logs
        ;;
    logs-view)
        view_logs_recent
        ;;
    logs-search)
        search_logs "$2"
        ;;
    logs-clear)
        clear_logs
        ;;
    screenshot)
        capture_screenshot
        ;;
    screenshots)
        list_screenshots
        ;;
    analytics)
        view_analytics
        ;;
    visitors)
        list_visitors
        ;;
    visitor-info)
        visitor_info "$2"
        ;;
    *)
        usage
        ;;
esac
