#!/bin/bash
# test_config_changes.sh

# Test configuration
APP="debox-firefox"
CONFIG_KEY="permissions.network"

# Colors
GREEN="\033[0;32m"
RED="\033[0;31m"
NC="\033[0m"

echo "--- TEST 1: Configuration change (enable network) ---"

# 1. Set to TRUE
echo "-> Setting $CONFIG_KEY = true"
# We use the --verbose flag to see errors, but redirect stdout
debox configure $APP --key $CONFIG_KEY --set true > /dev/null
debox apply $APP > /dev/null

# JSON Verification: Looking for .HostConfig.NetworkMode
NET_MODE=$(podman inspect $APP --format '{{.HostConfig.NetworkMode}}')

if [ "$NET_MODE" == "default" ] || [ "$NET_MODE" == "slirp4netns" ] || [ "$NET_MODE" == "pasta" ] || [ -z "$NET_MODE" ]; then
    # Empty NetworkMode or "default" means network is enabled in rootless Podman
    echo -e "${GREEN}✅ Verification 1: Container has network (Mode: '$NET_MODE').${NC}"
else
    echo -e "${RED}❌ ERROR 1: Container has no network (Mode: '$NET_MODE')!${NC}"
    exit 1
fi

echo -e "\n--- TEST 2: Configuration change (disable network) ---"

# 2. Set to FALSE
echo "-> Setting $CONFIG_KEY = false"
debox configure $APP --key $CONFIG_KEY --set false > /dev/null
debox apply $APP > /dev/null

# JSON Verification
NET_MODE=$(podman inspect $APP --format '{{.HostConfig.NetworkMode}}')

if [ "$NET_MODE" == "none" ]; then
    echo -e "${GREEN}✅ Verification 2: Container has no network (Mode: 'none').${NC}"
else
    echo -e "${RED}❌ ERROR 2: Container still has network (Mode: '$NET_MODE')!${NC}"
    exit 1
fi

echo -e "\n--- TEST 3: Command 'debox network allow' ---"

debox network allow $APP > /dev/null
NET_MODE=$(podman inspect $APP --format '{{.HostConfig.NetworkMode}}')

if [ "$NET_MODE" != "none" ]; then
    echo -e "${GREEN}✅ Verification 3: Network enabled via 'network allow'.${NC}"
else
    echo -e "${RED}❌ ERROR 3: 'network allow' did not work.${NC}"
    exit 1
fi

echo -e "\n--- TEST 4: Command 'debox network deny' ---"

debox network deny $APP > /dev/null
NET_MODE=$(podman inspect $APP --format '{{.HostConfig.NetworkMode}}')

if [ "$NET_MODE" == "none" ]; then
    echo -e "${GREEN}✅ Verification 4: Network disabled via 'network deny'.${NC}"
else
    echo -e "${RED}❌ ERROR 4: 'network deny' did not work.${NC}"
    exit 1
fi

echo -e "\n--- TEST 5: Idempotency (No changes needed) ---"
echo "-> Running 'debox apply' without changes..."
OUTPUT=$(debox apply $APP 2>&1) # Capture stderr as well
if echo "$OUTPUT" | grep -q "No changes needed"; then
    echo -e "${GREEN}✅ Verification 5: Correctly detected no changes.${NC}"
else
    echo -e "${RED}❌ ERROR 5: 'apply' performed an action despite no changes.${NC}"
    # echo "DEBUG OUTPUT: $OUTPUT"
    exit 1
fi

echo -e "\n${GREEN}--- All tests completed successfully! ---${NC}"