#!/bin/bash

set -e

# --- Configuration ---
APP_NAME="debox"
# VERSION is now dynamic, read from changelog
ARCH="all"
# MAINTAINER is now dynamic, read from git
DESC="Container manager for desktop applications on Debian"
BUILD_DIR="build/debian"
SOURCE_DIR="debox"
DOCS_DIR="docs"

# System dependencies (Debian Trixie)
DEPENDS="python3, podman, python3-typer, python3-rich, python3-yaml, python3-requests, python3-pil"

# Colors
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
BLUE="\033[0;34m"
RED="\033[0;31m"
NC="\033[0m"

# --- Helper Functions ---

setup_git_identity() {
    # 1. Fetch identity from Git config for dch
    echo "-> Configuring packaging identity..."
    if [ -z "$DEBFULLNAME" ]; then
        export DEBFULLNAME=$(git config user.name)
    fi
    if [ -z "$DEBEMAIL" ]; then
        export DEBEMAIL=$(git config user.email)
    fi

    if [ -z "$DEBFULLNAME" ] || [ -z "$DEBEMAIL" ]; then
        echo -e "${RED}Error: Git user.name or user.email not set. Cannot maintain changelog.${NC}"
        exit 1
    fi
    echo "   Identity: $DEBFULLNAME <$DEBEMAIL>"
}

ensure_debian_structure() {
    # 3. Create debian/changelog if missing
    mkdir -p debian
    
    if [ ! -f "debian/changelog" ]; then
        echo -e "${YELLOW}-> Initializing debian/changelog...${NC}"
        # Start with 0.1.0-1 if not exists
        dch --create --package "$APP_NAME" --newversion "0.1.0-1" --distribution trixie "Initial release."
    fi
}

auto_bump_version() {
    # 2. Check logic: Has anything changed since the last release mentioned in changelog?
    # We compare HEAD with the commit hash of the last tag matching the version.
    
    CURRENT_VERSION=$(dpkg-parsechangelog -S Version)
    # Assuming tags are named 'vX.Y.Z-R' or just 'vX.Y.Z'
    # Since we don't have tags perfectly synced yet, we check if git is clean.
    
    if git diff-index --quiet HEAD --; then
        echo -e "${BLUE}-> Repository is clean. Building version $CURRENT_VERSION.${NC}"
    else
        echo -e "${YELLOW}-> Changes detected in repository.${NC}"
        echo "   Autobumping Patch Version (e.g. 0.1.2 -> 0.1.3)"
        
        # Determine increment strategy. 
        # dch -i increments revision (1.0-1 -> 1.0-2). 
        # To increment upstream version (1.0.1 -> 1.0.2), we need logic or use a helper.
        # Here we use a simple patch bump approach using python or string manipulation would be better,
        # but for simplicity, we rely on dch -v.
        
        # Let's extract upstream version
        BASE_VER=$(echo "$CURRENT_VERSION" | cut -d- -f1)
        REV=$(echo "$CURRENT_VERSION" | cut -d- -f2)
        
        # Split BASE_VER by dots
        IFS='.' read -r -a PARTS <<< "$BASE_VER"
        MAJOR=${PARTS[0]}
        MINOR=${PARTS[1]}
        PATCH=${PARTS[2]}
        
        NEW_PATCH=$((PATCH + 1))
        NEW_UPSTREAM="${MAJOR}.${MINOR}.${NEW_PATCH}"
        NEW_FULL_VER="${NEW_UPSTREAM}-1"
        
        echo "   Bumping to $NEW_FULL_VER"
        
        dch --newversion "$NEW_FULL_VER" --distribution trixie "Minor changes (Auto-bump during build)."

        git add debian/changelog
        git commit -m "Bump version to $NEW_FULL_VER"

        # Update variable
        CURRENT_VERSION="$NEW_FULL_VER"
    fi

    # Autotag
    git tag -s "v$CURRENT_VERSION" -m "Release $CURRENT_VERSION"
}

# --- Main Execution ---

echo -e "${YELLOW}--- Starting Debox Build Process ---${NC}"

# Check for required tools
command -v dch >/dev/null 2>&1 || { echo -e "${RED}Error: 'devscripts' package (dch) is missing.${NC}"; exit 1; }
command -v dpkg-parsechangelog >/dev/null 2>&1 || { echo -e "${RED}Error: 'dpkg-dev' package is missing.${NC}"; exit 1; }

setup_git_identity
ensure_debian_structure
auto_bump_version

# Read the final version from changelog (in case it was bumped)
VERSION=$(dpkg-parsechangelog -S Version)
DEB_FILENAME="${APP_NAME}_${VERSION}_${ARCH}.deb"

echo -e "${BLUE}-> Building Version: ${VERSION}${NC}"

# 1. Prepare clean build directory
echo "-> Preparing build directory..."
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/DEBIAN"
mkdir -p "$BUILD_DIR/usr/bin"
mkdir -p "$BUILD_DIR/usr/lib/$APP_NAME"
mkdir -p "$BUILD_DIR/usr/share/man/man1"
mkdir -p "$BUILD_DIR/usr/share/man/man5"

# 2. Generate Binary Control File
# Instead of copying and mutating the source control file (which has multiple stanzas),
# we generate a clean binary control file specifically for dpkg-deb.
# This ensures strict adherence to binary package format (single stanza, starting with Package).

echo "-> Generating binary control file at $BUILD_DIR/DEBIAN/control..."

# We need to grab Section and Priority from variables or hardcode them if they match source.
# Based on your source control file:
SECTION="utils"
PRIORITY="optional"

cat <<EOF > "$BUILD_DIR/DEBIAN/control"
Package: $APP_NAME
Version: $VERSION
Architecture: $ARCH
Maintainer: $DEBFULLNAME <$DEBEMAIL>
Depends: $DEPENDS
Section: $SECTION
Priority: $PRIORITY
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