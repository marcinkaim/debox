#!/bin/bash

set -e

# Load secrets
if [ -f ".secrets" ]; then
    source .secrets
else
    echo "Error: .secrets file not found!"
    exit 1
fi

# Dependencies check
command -v jq >/dev/null 2>&1 || { echo "Error: 'jq' is required."; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "Error: 'curl' is required."; exit 1; }

# Colors
GREEN="\033[0;32m"
BLUE="\033[0;34m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
NC="\033[0m"

# Get Version Info
VERSION=$(dpkg-parsechangelog -S Version)
TAG_NAME="v${VERSION}"
# Architecture can be hardcoded or detected. Using 'all' based on your control file.
ARCH="all" 
DEB_FILENAME="debox_${VERSION}_${ARCH}.deb"
ASC_FILENAME="${DEB_FILENAME}.asc"

RELEASE_TITLE="Release ${VERSION}"
RELEASE_BODY="Auto-generated release for version ${VERSION}.\n\nIntegrity verification:\n\`gpg --verify ${ASC_FILENAME} ${DEB_FILENAME}\`"

# API Config
API_URL="https://api.github.com/repos/${GITHUB_USER}/${GITHUB_REPO}/releases"
HEADER_AUTH="Authorization: token ${GITHUB_TOKEN}"
HEADER_ACCEPT="Accept: application/vnd.github.v3+json"

echo -e "${BLUE}--- GitHub Release Process for ${TAG_NAME} ---${NC}"

# 1. Check if release already exists
echo "-> Checking existing releases..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -H "$HEADER_AUTH" -H "$HEADER_ACCEPT" "${API_URL}/tags/${TAG_NAME}")

if [ "$HTTP_CODE" == "200" ]; then
    echo -e "${YELLOW}Warning: Release ${TAG_NAME} already exists.${NC}"
    # Retrieve existing release data to get upload_url
    RELEASE_DATA=$(curl -s -H "$HEADER_AUTH" -H "$HEADER_ACCEPT" "${API_URL}/tags/${TAG_NAME}")
    RELEASE_ID=$(echo "$RELEASE_DATA" | jq .id)
    UPLOAD_URL_TEMPLATE=$(echo "$RELEASE_DATA" | jq -r .upload_url)
else
    # 2. Create New Release
    echo "-> Creating new release..."
    JSON_PAYLOAD=$(jq -n \
                  --arg tag "$TAG_NAME" \
                  --arg name "$RELEASE_TITLE" \
                  --arg body "$RELEASE_BODY" \
                  '{tag_name: $tag, name: $name, body: $body, draft: false, prerelease: false}')

    RESPONSE=$(curl -s -X POST "${API_URL}" \
        -H "$HEADER_AUTH" \
        -H "$HEADER_ACCEPT" \
        -H "Content-Type: application/json" \
        -d "$JSON_PAYLOAD")

    RELEASE_ID=$(echo "$RESPONSE" | jq .id)
    UPLOAD_URL_TEMPLATE=$(echo "$RESPONSE" | jq -r .upload_url)
    
    if [ "$RELEASE_ID" == "null" ]; then
        echo -e "${RED}Error creating release. Response:${NC}"
        echo "$RESPONSE"
        exit 1
    fi
    echo "   Release ID: $RELEASE_ID"
fi

# 3. Upload Assets Loop
# Clean up upload URL (remove templating {...})
UPLOAD_URL_BASE=$(echo "$UPLOAD_URL_TEMPLATE" | sed -e 's/{?name,label}//')

# Define assets to upload: "Filename|MimeType"
ASSETS=(
    "${DEB_FILENAME}|application/vnd.debian.binary-package"
    "${ASC_FILENAME}|application/pgp-signature"
)

echo "-> Starting upload of ${#ASSETS[@]} assets..."

for ASSET_DEF in "${ASSETS[@]}"; do
    FILE_PATH="${ASSET_DEF%%|*}"
    MIME_TYPE="${ASSET_DEF##*|}"
    
    if [ ! -f "$FILE_PATH" ]; then
        echo -e "${RED}Error: Asset file '$FILE_PATH' not found! Skipping.${NC}"
        continue
    fi

    echo "   -> Uploading: $FILE_PATH ($MIME_TYPE)..."
    
    # Check if asset already exists (to avoid 422 errors on re-run)
    # Simple check: delete previous asset with same name? Or just overwrite?
    # GitHub API rejects overwrite with 422 Validation Failed. 
    # For simplicity in this script, we assume clean upload or manual cleanup if failed.
    # To be robust, one would list assets and delete ID if matches name.
    
    curl -s -X POST "${UPLOAD_URL_BASE}?name=${FILE_PATH}" \
        -H "$HEADER_AUTH" \
        -H "Content-Type: ${MIME_TYPE}" \
        --data-binary "@${FILE_PATH}" | jq -r '.name // .message' | while read OUTPUT; do
            if [ "$OUTPUT" == "$FILE_PATH" ]; then
                 echo -e "      ${GREEN}OK${NC}"
            else
                 echo -e "      ${YELLOW}Response: $OUTPUT${NC}"
            fi
        done
done

echo -e "${GREEN}✅ Release process completed.${NC}"