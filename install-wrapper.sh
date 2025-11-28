#!/bin/bash
# Install askplexi CLI wrapper to make it available system-wide
# Usage: ./install-wrapper.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "Perplexity API - CLI Wrapper Installer"
echo "======================================"
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
VENV_DIR="$PROJECT_DIR/.venv"
ASKPLEXI_BIN="$VENV_DIR/bin/askplexi"

# Check if venv exists
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${RED}Error: Virtual environment not found at $VENV_DIR${NC}"
    echo "Please create the venv and install the package first:"
    echo "  python3 -m venv .venv"
    echo "  source .venv/bin/activate"
    echo "  pip install ."
    exit 1
fi

# Check if askplexi is installed in venv
if [ ! -f "$ASKPLEXI_BIN" ]; then
    echo -e "${RED}Error: askplexi not found in venv at $ASKPLEXI_BIN${NC}"
    echo "Please install the package first:"
    echo "  source .venv/bin/activate"
    echo "  pip install ."
    exit 1
fi

echo "Installation Configuration:"
echo "  Project directory: $PROJECT_DIR"
echo "  Virtual environment: $VENV_DIR"
echo "  askplexi binary: $ASKPLEXI_BIN"
echo ""

# Determine shell config file
SHELL_CONFIG=""
if [ -n "$ZSH_VERSION" ]; then
    SHELL_CONFIG="$HOME/.zshrc"
elif [ -n "$BASH_VERSION" ]; then
    SHELL_CONFIG="$HOME/.bashrc"
else
    SHELL_CONFIG="$HOME/.profile"
fi

echo "Installation Options:"
echo "  1) Add venv/bin to PATH in $SHELL_CONFIG (recommended)"
echo "  2) Create symlink in ~/.local/bin (no PATH modification)"
echo ""

read -p "Choose installation method (1 or 2, default: 1): " -n 1 -r
echo
METHOD="${REPLY:-1}"

if [ "$METHOD" = "1" ]; then
    # Option 1: Add to PATH in shell config
    EXPORT_LINE="export PATH=\"$VENV_DIR/bin:\$PATH\""
    
    # Check if already added
    if grep -q "$VENV_DIR/bin" "$SHELL_CONFIG" 2>/dev/null; then
        echo -e "${YELLOW}PATH entry already exists in $SHELL_CONFIG${NC}"
        read -p "Do you want to update it? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            # Remove old entry if exists
            sed -i "\|$VENV_DIR/bin|d" "$SHELL_CONFIG" 2>/dev/null || true
            # Add new entry
            echo "" >> "$SHELL_CONFIG"
            echo "# Perplexity API CLI wrapper" >> "$SHELL_CONFIG"
            echo "$EXPORT_LINE" >> "$SHELL_CONFIG"
            echo -e "${GREEN}✓ Updated PATH in $SHELL_CONFIG${NC}"
        else
            echo "Installation cancelled."
            exit 0
        fi
    else
        # Add to shell config
        echo "" >> "$SHELL_CONFIG"
        echo "# Perplexity API CLI wrapper" >> "$SHELL_CONFIG"
        echo "$EXPORT_LINE" >> "$SHELL_CONFIG"
        echo -e "${GREEN}✓ Added PATH entry to $SHELL_CONFIG${NC}"
    fi
    
    echo ""
    echo -e "${GREEN}Installation complete!${NC}"
    echo ""
    echo "To use askplexi in the current shell, run:"
    echo "  source $SHELL_CONFIG"
    echo ""
    echo "Or open a new terminal and use:"
    echo "  askplexi \"your question\""
    echo ""
    echo "Session management:"
    echo "  askplexi \"question\"              # Creates a new session"
    echo "  askplexi \"question\" --continue  # Continues last session"
    echo "  askplexi \"question\" --id SESSION_ID  # Continues specific session"
    
elif [ "$METHOD" = "2" ]; then
    # Option 2: Create symlink in ~/.local/bin
    LOCAL_BIN="$HOME/.local/bin"
    SYMLINK_TARGET="$LOCAL_BIN/askplexi"
    
    # Create ~/.local/bin if it doesn't exist
    mkdir -p "$LOCAL_BIN"
    
    # Check if symlink already exists
    if [ -L "$SYMLINK_TARGET" ] || [ -f "$SYMLINK_TARGET" ]; then
        echo -e "${YELLOW}Symlink already exists at $SYMLINK_TARGET${NC}"
        read -p "Do you want to overwrite it? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -f "$SYMLINK_TARGET"
        else
            echo "Installation cancelled."
            exit 0
        fi
    fi
    
    # Create symlink
    ln -s "$ASKPLEXI_BIN" "$SYMLINK_TARGET"
    echo -e "${GREEN}✓ Created symlink: $SYMLINK_TARGET -> $ASKPLEXI_BIN${NC}"
    
    # Check if ~/.local/bin is in PATH
    if [[ ":$PATH:" != *":$LOCAL_BIN:"* ]]; then
        echo ""
        echo -e "${YELLOW}Note: ~/.local/bin may not be in your PATH${NC}"
        echo "If askplexi doesn't work, add this to $SHELL_CONFIG:"
        echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    fi
    
    echo ""
    echo -e "${GREEN}Installation complete!${NC}"
    echo ""
    echo "You can now use askplexi from anywhere:"
    echo "  askplexi \"your question\""
    echo ""
    echo "Session management:"
    echo "  askplexi \"question\"              # Creates a new session"
    echo "  askplexi \"question\" --continue  # Continues last session"
    echo "  askplexi \"question\" --id SESSION_ID  # Continues specific session"
    
else
    echo -e "${RED}Invalid option. Installation cancelled.${NC}"
    exit 1
fi

echo ""
echo "Test the installation with:"
echo "  askplexi \"hi\""

