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

# --- CASE A: Runtime Change (Environment Variable) ---
log "Case A: Changing runtime.environment"
debox configure $APP --key runtime.environment --map "TEST_ENV=1" > /dev/null
debox apply $APP > /dev/null

NEW_CID=$(podman inspect $APP --format "{{.Id}}")
NEW_IID=$(podman inspect localhost/$APP:latest --format "{{.Id}}")

if [ "$OLD_CID" != "$NEW_CID" ]; then
    echo -e "${GREEN}✅ PASS: Container recreated (correctly).${NC}"
else
    echo -e "${RED}❌ FAIL: Container was NOT recreated!${NC}"
    exit 1
fi

if [ "$OLD_IID" == "$NEW_IID" ]; then
    echo -e "${GREEN}✅ PASS: Image preserved (optimization).${NC}"
else
    echo -e "${RED}❌ FAIL: Image unnecessarily rebuilt!${NC}"
    exit 1
fi

# Update 'old' CID to current for the next test
OLD_CID=$NEW_CID

# --- CASE B: Permissions Change (Network) ---
log "Case B: Changing permissions.network"
# Toggle to opposite (if true then false, etc.)
CURRENT_NET=$(podman inspect $APP --format '{{.HostConfig.NetworkMode}}')
if [ "$CURRENT_NET" == "none" ]; then TARGET="true"; else TARGET="false"; fi

debox configure $APP --key permissions.network --set $TARGET > /dev/null
debox apply $APP > /dev/null

NEW_CID=$(podman inspect $APP --format "{{.Id}}")
if [ "$OLD_CID" != "$NEW_CID" ]; then
    echo -e "${GREEN}✅ PASS: Container recreated (permissions change).${NC}"
else
    echo -e "${RED}❌ FAIL: Container was NOT recreated!${NC}"
    exit 1
fi
OLD_CID=$NEW_CID

# --- CASE C: Critical Integration (Desktop Integration) ---
log "Case C: Changing integration.desktop_integration (Test 'Critical Integration Hash')"
# This is in 'integration' section, but should force recreation (as it changes mounts)
debox configure $APP --key integration.desktop_integration --set false > /dev/null
debox apply $APP > /dev/null

NEW_CID=$(podman inspect $APP --format "{{.Id}}")
if [ "$OLD_CID" != "$NEW_CID" ]; then
    echo -e "${GREEN}✅ PASS: Container recreated (critical integration change).${NC}"
else
    echo -e "${RED}❌ FAIL: Container was NOT recreated, but should have been!${NC}"
    echo "   Check 'integration_critical' logic in hash_utils.py"
    exit 1
fi

# Cleanup
log "Cleanup..."
debox configure $APP --key runtime.environment --unmap "TEST_ENV" > /dev/null
debox configure $APP --key permissions.network --set true > /dev/null
debox configure $APP --key integration.desktop_integration --set true > /dev/null
debox apply $APP > /dev/null