#!/bin/bash
# Build Physio Script as macOS .app + DMG installer
#
# Usage:
#   chmod +x build_dmg.sh
#   ./build_dmg.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================"
echo "  Physio Script - DMG Builder"
echo "========================================"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: python3 not found"
    exit 1
fi

# Check pyinstaller
if ! python3 -c "import PyInstaller" 2>/dev/null; then
    echo "Installing PyInstaller..."
    pip install pyinstaller
fi

# Clean previous builds
echo ""
echo "Cleaning previous builds..."
rm -rf dist/ build/

# Build the app
echo ""
echo "Building PhysioScript.app..."
python3 -m PyInstaller \
    --clean \
    --noconfirm \
    --windowed \
    --name "PhysioScript" \
    --specpath "." \
    --distpath "./dist" \
    --workpath "./build" \
    physio_script.spec

APP_PATH="dist/PhysioScript.app"

if [ ! -d "$APP_PATH" ]; then
    echo "ERROR: .app bundle not found"
    exit 1
fi

echo ""
echo "Build successful: $APP_PATH"

# Create DMG
echo ""
echo "Creating DMG installer..."

DMG_NAME="PhysioScript-Installer.dmg"
DMG_PATH="dist/$DMG_NAME"

# Remove old DMG
rm -f "$DMG_PATH"

# Create temporary staging directory
TEMP_DIR="dist/temp_dmg"
rm -rf "$TEMP_DIR"
mkdir -p "$TEMP_DIR"

# Copy app
cp -R "$APP_PATH" "$TEMP_DIR/"

# Create Applications symlink
ln -s /Applications "$TEMP_DIR/Applications"

# Create DMG
hdiutil create \
    -volname "Physio Script" \
    -srcfolder "$TEMP_DIR" \
    -ov \
    -format UDZO \
    "$DMG_PATH"

# Cleanup
rm -rf "$TEMP_DIR"

echo ""
echo "========================================"
echo "  Build Complete!"
echo "========================================"
echo ""
echo "  App: $APP_PATH"
echo "  DMG: $DMG_PATH"
echo ""
echo "  To install: Open the DMG and drag PhysioScript to Applications"
echo "  To run: Double-click PhysioScript.app"
echo ""
echo "  Note: Ollama must be running separately on your machine."
echo ""
