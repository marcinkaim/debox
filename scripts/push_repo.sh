#!/bin/bash

set -e

# Load secrets
if [ -f ".secrets" ]; then
    source .secrets
else
    echo "Error: .secrets file not found!"
    exit 1
fi

# Configuration
REMOTE_NAME="origin"
REMOTE_URL="https://github.com/${GITHUB_USER}/${GITHUB_REPO}.git"
# Auth URL used ONLY for the push command, strictly in memory/env
AUTH_REMOTE_URL="https://${GITHUB_USER}:${GITHUB_TOKEN}@github.com/${GITHUB_USER}/${GITHUB_REPO}.git"

# Colors
GREEN="\033[0;32m"
BLUE="\033[0;34m"
NC="\033[0m"

echo -e "${BLUE}--- Git Sync Process ---${NC}"

# 1. Configure Remote (Standard URL without secrets)
if ! git remote | grep -q "^${REMOTE_NAME}$"; then
    echo "-> Remote '${REMOTE_NAME}' not found. Adding..."
    git remote add "${REMOTE_NAME}" "${REMOTE_URL}"
else
    # Update url just in case
    echo "-> Remote '${REMOTE_NAME}' exists. Ensuring URL is correct..."
    git remote set-url "${REMOTE_NAME}" "${REMOTE_URL}"
fi

# 2. Push Code and Tags using Token
# We verify if we are on a branch
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)

echo "-> Pushing branch: ${CURRENT_BRANCH}..."
git push "${AUTH_REMOTE_URL}" "${CURRENT_BRANCH}"

echo "-> Pushing tags..."
git push "${AUTH_REMOTE_URL}" --tags

echo -e "${GREEN}✅ Repository synced with GitHub.${NC}"