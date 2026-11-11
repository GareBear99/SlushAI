#!/usr/bin/env bash
# AI3DModeller Viewer Control Script

set -e
cd "$(dirname "$0")/.."

VENV_ACTIVATE=".venv/bin/activate"
VIEWER_DIR="viewer"
PID_FILE="/tmp/ai3dmodeller_viewer.pid"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

case "${1:-}" in
    start)
        if [ -f "$PID_FILE" ]; then
            PID=$(cat "$PID_FILE")
            if ps -p "$PID" > /dev/null 2>&1; then
                echo -e "${YELLOW}⚠️  Viewer is already running (PID: $PID)${NC}"
                echo -e "${BLUE}🌐 Open: http://localhost:5000${NC}"
                exit 0
            fi
        fi
        
        echo -e "${BLUE}🚀 Starting AI3DModeller Viewer...${NC}"
        source "$VENV_ACTIVATE"
        
        # Start server in background
        cd "$VIEWER_DIR"
        nohup python app.py > ../logs/viewer.log 2>&1 &
        PID=$!
        echo $PID > "$PID_FILE"
        
        # Wait a moment for server to start
        sleep 2
        
        if ps -p "$PID" > /dev/null 2>&1; then
            echo -e "${GREEN}✅ Viewer started successfully!${NC}"
            echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
            echo -e "${GREEN}🌐 Web Viewer: ${BLUE}http://localhost:5000${NC}"
            echo -e "${GREEN}📁 Models: ${NC}outputs/"
            echo -e "${GREEN}🔧 PID: ${NC}$PID"
            echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
            echo -e "${YELLOW}💡 Tip: Run 'scripts/viewer.sh open' to open in browser${NC}"
            
            # Auto-open browser on macOS
            if [[ "$OSTYPE" == "darwin"* ]]; then
                sleep 1
                open "http://localhost:5000"
            fi
        else
            echo -e "${RED}❌ Failed to start viewer${NC}"
            exit 1
        fi
        ;;
    
    stop)
        if [ ! -f "$PID_FILE" ]; then
            echo -e "${YELLOW}⚠️  Viewer is not running${NC}"
            exit 0
        fi
        
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo -e "${BLUE}🛑 Stopping viewer (PID: $PID)...${NC}"
            kill "$PID"
            rm "$PID_FILE"
            echo -e "${GREEN}✅ Viewer stopped${NC}"
        else
            echo -e "${YELLOW}⚠️  Viewer is not running (stale PID file)${NC}"
            rm "$PID_FILE"
        fi
        ;;
    
    restart)
        echo -e "${BLUE}🔄 Restarting viewer...${NC}"
        $0 stop
        sleep 1
        $0 start
        ;;
    
    status)
        if [ -f "$PID_FILE" ]; then
            PID=$(cat "$PID_FILE")
            if ps -p "$PID" > /dev/null 2>&1; then
                echo -e "${GREEN}✅ Viewer is running${NC}"
                echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
                echo -e "${GREEN}🌐 URL: ${BLUE}http://localhost:5000${NC}"
                echo -e "${GREEN}🔧 PID: ${NC}$PID"
                echo -e "${GREEN}📊 Memory: ${NC}$(ps -o rss= -p $PID | awk '{print int($1/1024)" MB"}')"
                echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
            else
                echo -e "${RED}❌ Viewer is not running (stale PID file)${NC}"
                rm "$PID_FILE"
            fi
        else
            echo -e "${YELLOW}⚠️  Viewer is not running${NC}"
        fi
        ;;
    
    open)
        if [[ "$OSTYPE" == "darwin"* ]]; then
            open "http://localhost:5000"
            echo -e "${GREEN}✅ Opening viewer in browser...${NC}"
        elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
            xdg-open "http://localhost:5000"
            echo -e "${GREEN}✅ Opening viewer in browser...${NC}"
        else
            echo -e "${BLUE}🌐 Open this URL: http://localhost:5000${NC}"
        fi
        ;;
    
    logs)
        if [ -f "logs/viewer.log" ]; then
            echo -e "${BLUE}📋 Viewer logs (last 50 lines):${NC}"
            echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
            tail -n 50 logs/viewer.log
        else
            echo -e "${YELLOW}⚠️  No log file found${NC}"
        fi
        ;;
    
    *)
        echo -e "${BLUE}╔═══════════════════════════════════════════════════════════╗${NC}"
        echo -e "${BLUE}║${NC}           ${GREEN}AI3DModeller Viewer Control${NC}               ${BLUE}║${NC}"
        echo -e "${BLUE}╚═══════════════════════════════════════════════════════════╝${NC}"
        echo ""
        echo -e "${GREEN}Usage:${NC}"
        echo -e "  ${BLUE}scripts/viewer.sh${NC} ${YELLOW}<command>${NC}"
        echo ""
        echo -e "${GREEN}Commands:${NC}"
        echo -e "  ${YELLOW}start${NC}      Start the web viewer server"
        echo -e "  ${YELLOW}stop${NC}       Stop the web viewer server"
        echo -e "  ${YELLOW}restart${NC}    Restart the web viewer server"
        echo -e "  ${YELLOW}status${NC}     Check viewer status"
        echo -e "  ${YELLOW}open${NC}       Open viewer in browser"
        echo -e "  ${YELLOW}logs${NC}       Show viewer logs"
        echo ""
        echo -e "${GREEN}Examples:${NC}"
        echo -e "  ${BLUE}scripts/viewer.sh start${NC}    # Start viewer and auto-open browser"
        echo -e "  ${BLUE}scripts/viewer.sh status${NC}   # Check if running"
        echo -e "  ${BLUE}scripts/viewer.sh logs${NC}     # View recent logs"
        echo ""
        exit 1
        ;;
esac
