#!/bin/bash

set -e

# --- Configuration ---
APP_NAME="debox"
VERSION="0.1.0"
ARCH="all"
MAINTAINER="Marcin Kaim <>"
DESC="Container manager for desktop applications on Debian"
BUILD_DIR="build/debian"
SOURCE_DIR="debox"
DOCS_DIR="docs"
COMPLETION_SRC="debox/completion/debox-completion.bash"

# System dependencies (Debian Trixie)
DEPENDS="python3, podman, python3-typer, python3-rich, python3-yaml, python3-requests, python3-pil"

# Colors
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
NC="\033[0m"

echo -e "${YELLOW}--- Starting build of package ${APP_NAME}_${VERSION}_${ARCH}.deb ---${NC}"

# 1. Prepare clean build directory
echo "-> Cleaning build directory..."
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/DEBIAN"
mkdir -p "$BUILD_DIR/usr/bin"
mkdir -p "$BUILD_DIR/usr/lib/$APP_NAME"
mkdir -p "$BUILD_DIR/usr/share/man/man1"
mkdir -p "$BUILD_DIR/usr/share/bash-completion/completions"

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
 with seamless integration.
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
    mkdir -p "$BUILD_DIR/usr/share/man/man5"

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
dpkg-deb --build "$BUILD_DIR" "${APP_NAME}_${VERSION}_${ARCH}.deb"

echo -e "${GREEN}✅ Success! Package created: ${APP_NAME}_${VERSION}_${ARCH}.deb${NC}"