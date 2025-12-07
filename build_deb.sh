#!/bin/bash

set -e

# --- Configuration ---
APP_NAME="debox"
VERSION="0.1.0"
ARCH="all"
MAINTAINER="Marcin Kaim <9829098+marcinkaim@users.noreply.github.com>"
DESC="Container manager for desktop applications on Debian"
BUILD_DIR="build/debian"
SOURCE_DIR="debox"
DOCS_DIR="docs"

# Define the output filename clearly
DEB_FILENAME="${APP_NAME}_${VERSION}_${ARCH}.deb"

# System dependencies (Debian Trixie)
DEPENDS="python3, podman, python3-typer, python3-rich, python3-yaml, python3-requests, python3-pil"

# Colors
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
NC="\033[0m"

echo -e "${YELLOW}--- Starting build of package ${DEB_FILENAME} ---${NC}"

# 1. Prepare clean build directory
echo "-> Cleaning build directory..."
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/DEBIAN"
mkdir -p "$BUILD_DIR/usr/bin"
mkdir -p "$BUILD_DIR/usr/lib/$APP_NAME"
mkdir -p "$BUILD_DIR/usr/share/man/man1"
mkdir -p "$BUILD_DIR/usr/share/man/man5"

# 2. Generate control file
echo "-> Generating DEBIAN/control file..."
cat <<EOF > "$BUILD_DIR/DEBIAN/control"
Package: $APP_NAME
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Depends: $DEPENDS
Maintainer: $MAINTAINER
Description: $DESC
 Debox allows you to run desktop applications in isolated Podman containers
 with seamless integration (icons, mime types). It manages the container lifecycle,
 updates, and configuration using declarative YAML files.
EOF

# 3. Copy source code
echo "-> Copying source code to /usr/lib/$APP_NAME..."
cp -r "$SOURCE_DIR" "$BUILD_DIR/usr/lib/$APP_NAME/"
find "$BUILD_DIR/usr/lib/$APP_NAME" -name "__pycache__" -type d -exec rm -rf {} +

# 4. Create entry point script
echo "-> Creating entry point script /usr/bin/$APP_NAME..."
cat <<EOF > "$BUILD_DIR/usr/bin/$APP_NAME"
#!/bin/sh
# Wrapper script for debox
export PYTHONPATH="/usr/lib/$APP_NAME"
exec python3 -m debox.cli "\$@"
EOF
chmod 755 "$BUILD_DIR/usr/bin/$APP_NAME"

# 5. Generate Manual (Man Pages)
if command -v pandoc >/dev/null 2>&1; then
    echo "-> Generating man pages..."

    if [ -f "$DOCS_DIR/${APP_NAME}.1.md" ]; then
        echo "   -> debox.1"
        pandoc "$DOCS_DIR/${APP_NAME}.1.md" -s -t man -o "$BUILD_DIR/usr/share/man/man1/${APP_NAME}.1"
        gzip -f "$BUILD_DIR/usr/share/man/man1/${APP_NAME}.1"
    fi

    if [ -f "$DOCS_DIR/${APP_NAME}.yml.5.md" ]; then
        echo "   -> debox.yml.5"
        pandoc "$DOCS_DIR/${APP_NAME}.yml.5.md" -s -t man -o "$BUILD_DIR/usr/share/man/man5/${APP_NAME}.yml.5"
        gzip -f "$BUILD_DIR/usr/share/man/man5/${APP_NAME}.yml.5"
    fi
else
    echo "   WARNING: 'pandoc' is not installed. Skipping man page generation."
fi

# 6. Build package
echo "-> Building .deb package..."
dpkg-deb --build "$BUILD_DIR" "$DEB_FILENAME"

# 7. Sign package (GPG)
echo "-> Signing package with GPG..."
if command -v gpg >/dev/null 2>&1; then
    # Try to get the signing key from git config
    GPG_KEY=$(git config --get user.signingkey || true)
    
    SIGN_CMD="gpg --armor --detach-sign"
    
    if [ -n "$GPG_KEY" ]; then
        echo "   Using GPG key from git config: $GPG_KEY"
        SIGN_CMD="$SIGN_CMD --default-key $GPG_KEY"
    else
        echo "   No specific key found in git config. Using default GPG key."
    fi
    
    # Execute signing
    # This might prompt for a passphrase depending on your GPG agent settings
    $SIGN_CMD --output "${DEB_FILENAME}.asc" "$DEB_FILENAME"
    
    echo -e "${GREEN}✅ Signed: ${DEB_FILENAME}.asc${NC}"
else
    echo "   WARNING: 'gpg' not found. Skipping signature."
fi

echo -e "${GREEN}✅ Success! Package created: ${DEB_FILENAME}${NC}"
echo "To install: sudo apt install ./${DEB_FILENAME}"