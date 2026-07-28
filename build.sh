#!/bin/bash

# MudaleTunnel Linux Release Builder
set -e

echo "Building MudaleTunnel for Linux..."

# Create build directory
mkdir -p build/linux

# Copy source files
cp main.py build/linux/
cp MudaleTunnelUI.py build/linux/
cp tunnel_manager.py build/linux/ 2>/dev/null || true
cp web_app.py build/linux/ 2>/dev/null || true
cp config.py build/linux/ 2>/dev/null || true
cp requirements.txt build/linux/
cp README.md build/linux/
cp LICENSE build/linux/

# Create executable script
cat > build/linux/mudaletunnel << 'EOF'
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$SCRIPT_DIR/main.py" "$@"
EOF

chmod +x build/linux/mudaletunnel

# Create install script
cat > build/linux/install.sh << 'EOF'
#!/bin/bash
set -e

echo "Installing MudaleTunnel..."

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is required but not installed. Please install Python 3 first."
    exit 1
fi

# Install Python dependencies
pip3 install -r requirements.txt

# Copy to /usr/local/bin
sudo cp mudaletunnel /usr/local/bin/
sudo chmod +x /usr/local/bin/mudaletunnel

# Copy source files to /opt/mudaletunnel
sudo mkdir -p /opt/mudaletunnel
sudo cp *.py /opt/mudaletunnel/
sudo cp requirements.txt /opt/mudaletunnel/

# Update the executable to point to the correct location
sudo sed -i 's|SCRIPT_DIR=".*"|SCRIPT_DIR="/opt/mudaletunnel"|' /usr/local/bin/mudaletunnel

echo "MudaleTunnel installed successfully!"
echo "You can now run 'mudaletunnel' from anywhere."
EOF

chmod +x build/linux/install.sh

# Get version from setup.py or use default
VERSION=$(grep -E "version\s*=" setup.py 2>/dev/null | sed -E "s/.*version\s*=\s*['\"]([^'\"]+)['\"].*/\1/" || echo "1.0.0")

# Create tarball with dynamic version
cd build
tar -czf mudaletunnel-linux-v${VERSION}.tar.gz linux/
cd ..

echo "Linux release created: build/mudaletunnel-linux-v${VERSION}.tar.gz"
echo ""
echo "Usage examples:"
echo "  mudaletunnel interactive                    # Interactive mode"
echo "  mudaletunnel scan 192.168.1.1               # Scan only"
echo "  mudaletunnel scan 192.168.1.1 -u user -s host -p 22 -l 8080  # Full command"