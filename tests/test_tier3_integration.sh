#!/bin/bash
set -e

APP="debox-firefox"
GREEN="\033[0;32m"
RED="\033[0;31m"
YELLOW="\033[0;33m"
NC="\033[0m"

log() { echo -e "\n${YELLOW}[TEST] $1${NC}"; }

# Pre-check
if ! debox list | grep -q "$APP"; then
    echo "Application $APP must be installed."
    exit 1
fi

# 1. Get initial state
OLD_CID=$(podman inspect $APP --format "{{.Id}}")
OLD_IID=$(podman inspect localhost/$APP:latest --format "{{.Id}}")

# --- CASE A: Changing Aliases ---
log "Case A: Adding alias (integration.aliases)"
debox configure $APP --key integration.aliases --map "ff-test=firefox-esr" > /dev/null
debox apply $APP > /dev/null

NEW_CID=$(podman inspect $APP --format "{{.Id}}")
NEW_IID=$(podman inspect localhost/$APP:latest --format "{{.Id}}")

if [ "$OLD_CID" == "$NEW_CID" ] && [ "$OLD_IID" == "$NEW_IID" ]; then
    echo -e "${GREEN}✅ PASS: Container and image preserved (reintegration only).${NC}"
else
    echo -e "${RED}❌ FAIL: Unnecessary container recreation!${NC}"
    exit 1
fi

# --- CASE B: Changing Skip Categories ---
log "Case B: Adding skip_categories"
debox configure $APP --key integration.skip_categories --add "Game" > /dev/null
debox apply $APP > /dev/null

NEW_CID=$(podman inspect $APP --format "{{.Id}}")
if [ "$OLD_CID" == "$NEW_CID" ]; then
    echo -e "${GREEN}✅ PASS: Container preserved.${NC}"
else
    echo -e "${RED}❌ FAIL: Unnecessary container recreation!${NC}"
    exit 1
fi

# Cleanup (restoring state)
log "Cleanup..."
debox configure $APP --key integration.aliases --unmap "ff-test" > /dev/null
debox configure $APP --key integration.skip_categories --remove "Game" > /dev/null
debox apply $APP > /dev/null