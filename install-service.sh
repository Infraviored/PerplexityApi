#!/bin/bash
# Install Perplexity API Server as a user systemd service
# Usage: ./install-service.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "Perplexity API Server - User Systemd Service Installer"
echo "======================================================"
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"

# Get current user and home directory
SERVICE_USER="$USER"
SERVICE_HOME="$HOME"

# Default configuration
DEFAULT_HOST="0.0.0.0"
DEFAULT_PORT="8088"
SERVICE_NAME="perplexity-api"

echo "Installation Configuration:"
echo "  Project directory: $PROJECT_DIR"
echo "  Service user: $SERVICE_USER"
echo "  Service name: $SERVICE_NAME"
echo "  Host: $DEFAULT_HOST"
echo "  Port: $DEFAULT_PORT"
echo ""

# Ask for confirmation
read -p "Do you want to install the service? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Installation cancelled."
    exit 0
fi

# Check if service already exists
if systemctl --user list-unit-files | grep -q "^${SERVICE_NAME}.service"; then
    echo -e "${YELLOW}Service ${SERVICE_NAME} already exists.${NC}"
    read -p "Do you want to reinstall it? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Installation cancelled."
        exit 0
    fi
    # Stop and disable existing service
    systemctl --user stop ${SERVICE_NAME} 2>/dev/null || true
    systemctl --user disable ${SERVICE_NAME} 2>/dev/null || true
fi

# Create user systemd directory if it doesn't exist
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_USER_DIR"

# Create config directory and config file if it doesn't exist
CONFIG_DIR="$HOME/.config/askplexi"
CONFIG_FILE="$CONFIG_DIR/config.json"
mkdir -p "$CONFIG_DIR"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Creating config file..."
    # Get XDG data directory for browser profile
    if [ -n "$XDG_DATA_HOME" ]; then
        BROWSER_PROFILE="$XDG_DATA_HOME/askplexi/browser-profile"
    else
        BROWSER_PROFILE="$HOME/.local/share/askplexi/browser-profile"
    fi
    
    cat > "$CONFIG_FILE" <<CONFIGEOF
{
  "browser": {
    "perplexity_url": "https://www.perplexity.ai/?login-source=signupButton&login-new=false",
    "user_data_dir": "$BROWSER_PROFILE",
    "headless": true,
    "use_xvfb": true,
    "browser_load_wait_seconds": 5,
    "chrome_driver_path": null,
    "login_detect_timeout_seconds": 45
  },
  "perplexity": {
    "default_model": "Claude Sonnet 4.5",
    "default_reasoning": true,
    "question_input_timeout": 10,
    "response_wait_timeout": 300,
    "element_wait_timeout": 30
  }
}
CONFIGEOF
    echo -e "${GREEN}✓ Config file created: $CONFIG_FILE${NC}"
else
    echo -e "${YELLOW}Config file already exists: $CONFIG_FILE${NC}"
fi

# Create systemd service file
SERVICE_FILE="$SYSTEMD_USER_DIR/${SERVICE_NAME}.service"

echo "Creating systemd service file..."

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Perplexity API Server
After=network.target

[Service]
Type=notify
NotifyAccess=main
TimeoutStartSec=600
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$PATH"
Environment="HOME=$SERVICE_HOME"
ExecStart=$PROJECT_DIR/.venv/bin/perplexity-server --host $DEFAULT_HOST --port $DEFAULT_PORT
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF

echo -e "${GREEN}✓ Service file created: $SERVICE_FILE${NC}"

# Reload systemd user daemon
echo "Reloading systemd user daemon..."
systemctl --user daemon-reload

# Enable service
echo "Enabling service..."
systemctl --user enable ${SERVICE_NAME}

echo -e "${GREEN}✓ Service enabled${NC}"

# Ask if user wants to start the service
read -p "Do you want to start the service now? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Starting service..."
    systemctl --user start ${SERVICE_NAME}
    sleep 2
    
    if systemctl --user is-active --quiet ${SERVICE_NAME}; then
        echo -e "${GREEN}✓ Service started successfully${NC}"
        echo ""
        echo "Service status:"
        systemctl --user status ${SERVICE_NAME} --no-pager -l
    else
        echo -e "${RED}✗ Service failed to start${NC}"
        echo "Check logs with: journalctl --user -u ${SERVICE_NAME} -n 50"
        exit 1
    fi
else
    echo "Service installed but not started."
    echo "Start it manually with: systemctl --user start ${SERVICE_NAME}"
fi

echo ""
echo "=================================================="
echo -e "${GREEN}Installation complete!${NC}"
echo ""
echo "Useful commands:"
echo "  Start service:   systemctl --user start ${SERVICE_NAME}"
echo "  Stop service:    systemctl --user stop ${SERVICE_NAME}"
echo "  Restart service: systemctl --user restart ${SERVICE_NAME}"
echo "  View logs:       journalctl --user -u ${SERVICE_NAME} -f"
echo "  Check status:    systemctl --user status ${SERVICE_NAME}"
echo ""
echo "Note: The service will start automatically when you log in."
echo "To enable lingering (start without login), run:"
echo "  loginctl enable-linger $USER"
echo ""

