#!/bin/bash
set -e

APP="debox-firefox"
GREEN="\033[0;32m"
RED="\033[0;31m"
YELLOW="\033[0;33m"
NC="\033[0m"

log() { echo -e "\n${YELLOW}[TEST] $1${NC}"; }

# 1. Initial state
OLD_CID=$(podman inspect $APP --format "{{.Id}}")
OLD_IID=$(podman inspect localhost/$APP:latest --format "{{.Id}}")

# --- CASE A: Adding package (image.packages) ---
log "Case A: Adding package to image.packages (Requires rebuild)"
# Using small package 'tree' for speed
debox configure $APP --key image.packages --add "tree" > /dev/null
debox apply $APP > /dev/null

NEW_CID=$(podman inspect $APP --format "{{.Id}}")
NEW_IID=$(podman inspect localhost/$APP:latest --format "{{.Id}}")

# Image Verification
if [ "$OLD_IID" != "$NEW_IID" ]; then
    echo -e "${GREEN}✅ PASS: Image was rebuilt.${NC}"
else
    echo -e "${RED}❌ FAIL: Image was NOT rebuilt!${NC}"
    exit 1
fi

# Container Verification
if [ "$OLD_CID" != "$NEW_CID" ]; then
    echo -e "${GREEN}✅ PASS: Container was recreated (required after rebuild).${NC}"
else
    echo -e "${RED}❌ FAIL: Container was NOT recreated!${NC}"
    exit 1
fi

# Cleanup
log "Cleanup..."
debox configure $APP --key image.packages --remove "tree" > /dev/null
debox apply $APP > /dev/null