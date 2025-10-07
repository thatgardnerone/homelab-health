#!/bin/bash
# Homelab Health Checker Installation Script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="$SCRIPT_DIR/.venv"
HEALTH_SCRIPT="$SCRIPT_DIR/health_check.py"

echo "Installing Homelab Health Checker..."
echo "Installation directory: $SCRIPT_DIR"

# Create virtual environment
echo "Creating Python virtual environment..."
python3 -m venv "$VENV_PATH"

# Install dependencies
echo "Installing dependencies..."
"$VENV_PATH/bin/pip" install -q pyyaml docker

# Update shebang to use venv python
echo "Updating script shebang..."
VENV_PYTHON="$VENV_PATH/bin/python3"
sed -i "1s|.*|#!$VENV_PYTHON|" "$HEALTH_SCRIPT"

# Make script executable
chmod +x "$HEALTH_SCRIPT"

echo ""
echo "✓ Installation complete!"
echo ""
echo "Next steps:"
echo "1. Test the health checker:"
echo "   $HEALTH_SCRIPT"
echo ""
echo "2. To integrate with MOTD, run:"
echo "   sudo tee /etc/update-motd.d/89-health-check > /dev/null << 'EOF'"
echo "#!/bin/sh"
echo "HEALTH_SCRIPT=\"$HEALTH_SCRIPT\""
echo ""
echo "if [ -x \"\$HEALTH_SCRIPT\" ]; then"
echo "    \"\$HEALTH_SCRIPT\" 2>/dev/null || true"
echo "fi"
echo "EOF"
echo ""
echo "   sudo chmod +x /etc/update-motd.d/89-health-check"
echo ""
echo "3. Customize monitoring in: $SCRIPT_DIR/config.yaml"
