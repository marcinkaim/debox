#!/bin/bash

set -e

# --- Configuration ---
APP_NAME="debox"
ARCH="all"
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
    mkdir -p debian
    
    if [ ! -f "debian/changelog" ]; then
        echo -e "${YELLOW}-> Initializing debian/changelog...${NC}"
        dch --create --package "$APP_NAME" --newversion "0.1.0-1" --distribution trixie "Initial release."
    fi
}

auto_bump_version() {
    # Condition A: Repository MUST be clean (no uncommitted changes).
    # Condition B: HEAD must NOT be tagged already.
    
    echo "-> Checking repository state for auto-bump..."

    # Check A: Is Repo Dirty?
    # git diff-index --quiet HEAD returns 1 if there are changes, 0 if clean.
    if ! git diff-index --quiet HEAD --; then
        echo -e "${YELLOW}WARNING: Repository has uncommitted changes.${NC}"
        echo "   Skipping auto-bump and tagging to ensure reproducibility."
        echo "   Building package based on current debian/changelog state."
        return
    fi

    # Check B: Is HEAD tagged?
    # git describe --exact-match fails if no tag points exactly to HEAD.
    if git describe --exact-match --tags HEAD >/dev/null 2>&1; then
        CURRENT_TAG=$(git describe --exact-match --tags HEAD)
        echo -e "${BLUE}-> Commit is already tagged ($CURRENT_TAG).${NC}"
        echo "   Skipping bump. Building existing release."
        return
    fi

    # If we are here: Clean AND Untagged -> PROCEED TO BUMP
    echo -e "${BLUE}-> Repository is clean and untagged. Proceeding with release bump.${NC}"

    CURRENT_VERSION=$(dpkg-parsechangelog -S Version)
    
    # Extract upstream version parts
    BASE_VER=$(echo "$CURRENT_VERSION" | cut -d- -f1)
    # Parse Major.Minor.Patch
    IFS='.' read -r -a PARTS <<< "$BASE_VER"
    MAJOR=${PARTS[0]}
    MINOR=${PARTS[1]}
    PATCH=${PARTS[2]}
    
    # Increment Patch
    NEW_PATCH=$((PATCH + 1))
    NEW_UPSTREAM="${MAJOR}.${MINOR}.${NEW_PATCH}"
    NEW_FULL_VER="${NEW_UPSTREAM}-1"
    
    echo "   Bumping version: $CURRENT_VERSION -> $NEW_FULL_VER"
    
    # Update changelog
    dch --newversion "$NEW_FULL_VER" --distribution trixie "Minor changes (Auto-bump during build)."

    echo "   Updating README.md to version $NEW_FULL_VER..."
    sed -i "s/debox_[0-9]\+\.[0-9]\+\.[0-9]\+\(-[0-9]\+\)\?_all\.deb/debox_${NEW_FULL_VER}_all.deb/g" README.md
    git add README.md

    # Commit the changelog bump
    # Note: We are modifying the repo here, so it becomes dirty for a split second until we commit.
    git add debian/changelog
    git commit -m "Bump version to $NEW_FULL_VER"

    # Tag the release
    echo "   Tagging release v$NEW_FULL_VER..."
    git tag -s "v$NEW_FULL_VER" -m "Release $NEW_FULL_VER"
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

    MAN_DATE=$(LC_ALL=C date '+%B %Y')

    if [ -f "$DOCS_DIR/${APP_NAME}.1.md" ]; then
        echo "   -> debox.1"
        pandoc "$DOCS_DIR/${APP_NAME}.1.md" -s -t man \
            -V footer="Debox $VERSION" \
            -V date="$MAN_DATE" \
            -o "$BUILD_DIR/usr/share/man/man1/${APP_NAME}.1"
        
        gzip -f "$BUILD_DIR/usr/share/man/man1/${APP_NAME}.1"
    fi

    if [ -f "$DOCS_DIR/${APP_NAME}.yml.5.md" ]; then
        echo "   -> debox.yml.5"
        pandoc "$DOCS_DIR/${APP_NAME}.yml.5.md" -s -t man \
            -V footer="Debox $VERSION" \
            -V date="$MAN_DATE" \
            -o "$BUILD_DIR/usr/share/man/man5/${APP_NAME}.yml.5"
        
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