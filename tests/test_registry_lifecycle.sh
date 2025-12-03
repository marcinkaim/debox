#!/bin/bash

set -e

# Colors for readability
GREEN="\033[0;32m"
RED="\033[0;31m"
YELLOW="\033[0;33m"
NC="\033[0m"

IMAGE_NAME="debox-test-image"
LOCAL_TAG="localhost/${IMAGE_NAME}:latest"
REGISTRY_TAG="localhost:5000/${IMAGE_NAME}:latest"
CONFIG_FILE="tests/test-image.yml"

log() { echo -e "\n${YELLOW}[TEST] $1${NC}"; }
check_command() {
    if [ $? -eq 0 ]; then echo -e "${GREEN}OK${NC}"; else echo -e "${RED}FAILED${NC}"; exit 1; fi
}

# --- PRE-TEST CLEANUP ---
log "0. Cleaning up environment..."
debox image rm ${IMAGE_NAME} > /dev/null 2>&1 || true
podman rmi ${LOCAL_TAG} > /dev/null 2>&1 || true
# Also remove config dir to simulate a clean start
rm -rf ~/.config/debox/images/${IMAGE_NAME}

# --- TEST 1: Build & Push ---
log "1. Building image and pushing to registry (debox image build)..."
debox image build ${CONFIG_FILE}
check_command

# Verification in list
log "   Verifying presence in list (debox image list)..."
if debox image list | grep -q "${IMAGE_NAME}:latest"; then
    echo -e "${GREEN}OK: Image visible in registry.${NC}"
else
    echo -e "${RED}ERROR: Image did not appear in the list!${NC}"
    exit 1
fi

# --- TEST 2: Local Delete Simulation ---
log "2. Removing image from local Podman cache..."
podman rmi ${LOCAL_TAG}
if ! podman images | grep -q "${LOCAL_TAG}"; then
    echo -e "${GREEN}OK: Image removed locally.${NC}"
else
    echo -e "${RED}ERROR: Image still exists locally!${NC}"
    exit 1
fi

# --- TEST 3: Restore (Pull) ---
log "3. Restoring image from registry (debox image pull)..."
debox image pull ${IMAGE_NAME}
check_command

# Verification if returned to Podman
if podman images | grep -q "${IMAGE_NAME}"; then
    echo -e "${GREEN}OK: Image restored to Podman cache.${NC}"
else
    echo -e "${RED}ERROR: Image was not restored!${NC}"
    exit 1
fi

# --- TEST 4: Registry Remove ---
log "4. Removing image from registry (debox image rm)..."
debox image rm ${IMAGE_NAME}
check_command

# Verification in list (should be N/A or disappear depending on implementation)
log "   Verifying removal from list..."
# Here we expect 'Backed Up' to be 'No' or the image to disappear from the list (if orphaned)
# Since this is a base image (in ~/.config/debox/images), 'image list' should show it as N/A
OUTPUT=$(debox image list)
if echo "$OUTPUT" | grep "${IMAGE_NAME}" | grep -q "N/A"; then
     echo -e "${GREEN}OK: Image marked as removed (N/A).${NC}"
elif ! echo "$OUTPUT" | grep -q "${IMAGE_NAME}"; then
     # If we also removed the config folder (which remove_image_digest does), the image will disappear from the list completely
     # Let's check implementation. hash_utils.remove_image_digest removes only the key from the file.
     # But debox image list shows images based on the registry directory.
     # After removing the manifest, the repository name remains in the directory, but has no tags.
     # Our new listing logic hides empty repositories.
     echo -e "${GREEN}OK: Image disappeared from list (no tags).${NC}"
else
    echo -e "${RED}ERROR: Image still listed as available!${NC}"
    echo "$OUTPUT"
    exit 1
fi

# --- TEST 5: Prune ---
log "5. Pruning registry (debox image prune)..."
# Running to check if it doesn't throw errors
debox image prune
check_command

# --- FINAL CLEANUP ---
log "6. Cleaning up after tests..."
podman rmi ${LOCAL_TAG} > /dev/null 2>&1 || true
rm -rf ~/.config/debox/images/${IMAGE_NAME} # Remove trace of base image

echo -e "\n${GREEN}✅ REGISTRY TESTS COMPLETED SUCCESSFULLY!${NC}"