#!/bin/bash
# test_advanced_config.sh

APP="debox-firefox"
# We assume the internal .desktop file name for Firefox is firefox-esr.desktop
INTERNAL_DESKTOP_FILE="firefox-esr.desktop"
HOST_DESKTOP_FILE="$HOME/.local/share/applications/${APP}_${INTERNAL_DESKTOP_FILE}"

# Colors
GREEN="\033[0;32m"
RED="\033[0;31m"
YELLOW="\033[0;33m"
NC="\033[0m"

log_info() { echo -e "\n${YELLOW}--- $1 ---${NC}"; }

# Check if the application is installed
if ! debox list | grep -q "$APP"; then
    echo -e "${RED}Error: Application $APP is not installed. Please install it before testing.${NC}"
    exit 1
fi

# --- TEST 1: Environment variables (runtime.environment) ---
log_info "TEST 1: Adding environment variable (Requires container recreation)"

# 1. Get container ID before change
OLD_CID=$(podman inspect $APP --format "{{.Id}}")
echo "-> Old container ID: ${OLD_CID:0:12}"

# 2. Configure variable
echo "-> Setting variable TEST_VAR=debox_rulez"
debox configure $APP --key runtime.environment --map TEST_VAR=debox_rulez > /dev/null

# 3. Apply changes
debox apply $APP > /dev/null

# 4. Verification
# a) Is the variable inside the container?
if podman inspect $APP --format '{{.Config.Env}}' | grep -q "TEST_VAR=debox_rulez"; then
    echo -e "${GREEN}✅ Environment variable present in container.${NC}"
else
    echo -e "${RED}❌ ERROR: Environment variable was not set!${NC}"
    exit 1
fi

# b) Was the container recreated? (ID should be different)
NEW_CID=$(podman inspect $APP --format "{{.Id}}")
echo "-> New container ID: ${NEW_CID:0:12}"

if [ "$OLD_CID" != "$NEW_CID" ]; then
    echo -e "${GREEN}✅ Container successfully recreated.${NC}"
else
    echo -e "${RED}❌ ERROR: Container was NOT recreated (ID is the same)!${NC}"
    exit 1
fi

# 5. Cleanup (remove variable)
echo "-> Cleanup (removing variable)..."
debox configure $APP --key runtime.environment --unmap TEST_VAR > /dev/null
debox apply $APP > /dev/null


# --- TEST 2: Name skipping (integration.skip_names) ---
log_info "TEST 2: Hiding icon (Requires reintegration only)"

# Ensure the file exists at the beginning
if [ ! -f "$HOST_DESKTOP_FILE" ]; then
    echo -e "${RED}Prerequisite Error: File $HOST_DESKTOP_FILE does not exist. Cannot perform test.${NC}"
    exit 1
fi

# 1. Get container ID before change
OLD_CID=$(podman inspect $APP --format "{{.Id}}")
echo "-> Container ID before change: ${OLD_CID:0:12}"

# 2. Add name to skip list
echo "-> Adding '$INTERNAL_DESKTOP_FILE' to skip_names"
debox configure $APP --key integration.skip_names --add "$INTERNAL_DESKTOP_FILE" > /dev/null

# 3. Apply changes
debox apply $APP > /dev/null

# 4. Verification
# a) Did the .desktop file disappear?
if [ ! -f "$HOST_DESKTOP_FILE" ]; then
    echo -e "${GREEN}✅ .desktop file successfully removed from host.${NC}"
else
    echo -e "${RED}❌ ERROR: .desktop file still exists!${NC}"
    exit 1
fi

# b) Did the container REMAIN the same? (Should not be recreated)
NEW_CID=$(podman inspect $APP --format "{{.Id}}")
echo "-> Container ID after change:  ${NEW_CID:0:12}"

if [ "$OLD_CID" == "$NEW_CID" ]; then
    echo -e "${GREEN}✅ Container was NOT recreated (Correct optimization).${NC}"
else
    echo -e "${RED}❌ WARNING: Container was unnecessarily recreated (ID changed).${NC}"
    # This is not a critical error, but indicates a lack of optimization in apply_cmd.py
fi

# 5. Cleanup (restore icon)
echo "-> Cleanup (restoring icon)..."
debox configure $APP --key integration.skip_names --remove "$INTERNAL_DESKTOP_FILE" > /dev/null
debox apply $APP > /dev/null

if [ -f "$HOST_DESKTOP_FILE" ]; then
    echo -e "${GREEN}✅ Initial state restored.${NC}"
else
    echo -e "${RED}❌ Error restoring initial state.${NC}"
fi

echo -e "\n${GREEN}=== All advanced configuration tests completed successfully! ===${NC}"