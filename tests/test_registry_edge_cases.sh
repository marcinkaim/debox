#!/bin/bash

set -e

# --- Configuration ---
IMAGE_NAME="debox-fail-test"
CONFIG_FILE="tests/test-image-fail.yml"
REGISTRY_CONTAINER="debox-registry"

# Colors
GREEN="\033[0;32m"
RED="\033[0;31m"
YELLOW="\033[0;33m"
NC="\033[0m"

log() { echo -e "\n${YELLOW}[EDGE-TEST] $1${NC}"; }

# Assertion helpers
assert_fail() {
    if "$@"; then
        echo -e "${RED}ERROR: Command should fail, but it succeeded!${NC}"
        exit 1
    else
        echo -e "${GREEN}OK: Command correctly reported an error.${NC}"
    fi
}

assert_pass() {
    if "$@"; then
        echo -e "${GREEN}OK: Command succeeded.${NC}"
    else
        echo -e "${RED}ERROR: Command should succeed, but an error occurred!${NC}"
        exit 1
    fi
}

# --- PREPARATION ---
# Create temporary config
echo "version: 1
image_name: \"$IMAGE_NAME\"
image:
  base: \"debian:stable-slim\"
  packages: []" > $CONFIG_FILE

# Cleanup
debox image rm $IMAGE_NAME > /dev/null 2>&1 || true
rm -rf ~/.config/debox/images/$IMAGE_NAME


# === SCENARIO 1: Operations on non-existent resources ===
log "1. Attempting to push non-existent image..."
# We haven't built it yet, so push must fail
assert_fail debox image push $IMAGE_NAME

log "2. Attempting to pull non-existent image..."
assert_fail debox image pull "debox-non-existent-image"

log "3. Attempting to remove (rm) non-existent image..."
# This should fail because there is no digest or image
assert_fail debox image rm "debox-non-existent-image"


# === SCENARIO 2: Infrastructure Self-Healing (Registry Down) ===
log "4. Test Self-Healing: Stopping registry container..."
podman stop $REGISTRY_CONTAINER
# Ensure it is stopped
if podman ps --filter name=$REGISTRY_CONTAINER --format "{{.Status}}" | grep -q "Up"; then
    echo "Error: Failed to stop registry."
    exit 1
fi

log "   Attempting to list images (should start the registry)..."
# This command should detect the registry is down, start it, and return the result
assert_pass debox image list

# Verify if it started
if podman ps --filter name=$REGISTRY_CONTAINER --format "{{.Status}}" | grep -q "Up"; then
    echo -e "${GREEN}OK: Registry was automatically started.${NC}"
else
    echo -e "${RED}ERROR: Registry did not start!${NC}"
    exit 1
fi


# === SCENARIO 3: Desynchronization (Ghost Image) ===
# Simulating situation: Debox thinks the image exists (has digest), but it is missing from registry.
log "5. Preparation: Building a valid image..."
debox image build $CONFIG_FILE > /dev/null

log "   Sabotage: Manually removing image from registry (behind Debox's back)..."
# Fetch digest to remove it manually
DIGEST=$(curl -s -H "Accept: application/vnd.docker.distribution.manifest.v2+json" http://localhost:5000/v2/$IMAGE_NAME/manifests/latest | grep Docker-Content-Digest | awk '{print $2}' | tr -d '\r')
# Delete manifest manually via API
curl -s -X DELETE http://localhost:5000/v2/$IMAGE_NAME/manifests/$DIGEST > /dev/null

log "   Verifying 'debox image rm' behavior on remotely non-existent image..."
# Debox has the digest saved in file. It will try to delete it. Registry will return 404.
# We expect Debox to handle this (show warning), but CLEAN UP local file and succeed.
assert_pass debox image rm $IMAGE_NAME

# Check if digest file was removed
if [ -f ~/.config/debox/images/$IMAGE_NAME/.last_applied_state.json ]; then
     # File might exist, but shouldn't have registry_digest key.
     # For simplicity: check if running rm again throws "No saved digest" error
     log "   Checking if local trace was removed..."
     assert_fail debox image rm $IMAGE_NAME
else
     echo -e "${GREEN}OK: Local trace removed.${NC}"
fi


# === SCENARIO 4: Missing Digest (Fallback to API) ===
# Simulating situation: Image exists in registry, but Debox lost the digest file.
log "6. Preparation: Rebuilding image..."
debox image build $CONFIG_FILE > /dev/null

log "   Sabotage: Removing local state file..."
rm ~/.config/debox/images/$IMAGE_NAME/.last_applied_state.json

log "   Verifying 'debox image rm' (Fallback to API)..."
# Debox won't find the digest in file. It should query the API, fetch digest, and remove image.
assert_pass debox image rm $IMAGE_NAME

# Check if actually removed from registry (API should return 404)
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/v2/$IMAGE_NAME/manifests/latest)
if [ "$HTTP_CODE" -eq 404 ]; then
    echo -e "${GREEN}OK: Image actually removed from registry.${NC}"
else
    echo -e "${RED}ERROR: Image still exists in registry (code $HTTP_CODE)!${NC}"
    exit 1
fi


# --- FINAL CLEANUP ---
rm $CONFIG_FILE
rm -rf ~/.config/debox/images/$IMAGE_NAME
podman rmi localhost/$IMAGE_NAME:latest > /dev/null 2>&1 || true

echo -e "\n${GREEN}=== ALL EDGE-CASE TESTS COMPLETED SUCCESSFULLY ===${NC}"