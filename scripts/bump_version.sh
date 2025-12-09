#!/bin/bash
set -e

# Configuration
APP_NAME="debox"
# Ensure we are in project root
if [ ! -d "debian" ]; then
    echo "Error: debian/ directory not found. Run this from project root."
    exit 1
fi

# Setup Identity
export DEBFULLNAME=$(git config user.name)
export DEBEMAIL=$(git config user.email)

TYPE=$1
MSG=$2

if [ -z "$MSG" ]; then
    MSG="Update version $TYPE"
fi

current_ver=$(dpkg-parsechangelog -S Version)
base_ver=$(echo "$current_ver" | cut -d- -f1)
IFS='.' read -r -a PARTS <<< "$base_ver"
MAJOR=${PARTS[0]}
MINOR=${PARTS[1]}
PATCH=${PARTS[2]}

new_ver=""

case "$TYPE" in
    "major")
        NEW_MAJOR=$((MAJOR + 1))
        new_ver="${NEW_MAJOR}.0.0-1"
        ;;
    "minor")
        NEW_MINOR=$((MINOR + 1))
        new_ver="${MAJOR}.${NEW_MINOR}.0-1"
        ;;
    "patch"|"bugfix")
        NEW_PATCH=$((PATCH + 1))
        new_ver="${MAJOR}.${MINOR}.${NEW_PATCH}-1"
        ;;
    "rel"|"package")
        # Just bump debian revision (e.g. 1.0.0-1 -> 1.0.0-2)
        dch -i "$MSG"
        echo "Bumped Debian revision."
        exit 0
        ;;
    *)
        echo "Usage: $0 {major|minor|patch|rel} [message]"
        exit 1
        ;;
esac

echo "Bumping version: $current_ver -> $new_ver"
dch --newversion "$new_ver" --distribution trixie "$MSG"

git add debian/changelog
git commit -m "Bump version to $new_ver"
git tag -s "v$new_ver" -m "Release $new_ver"