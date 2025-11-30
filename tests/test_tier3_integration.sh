#!/bin/bash
set -e

APP="debox-firefox"
GREEN="\033[0;32m"
RED="\033[0;31m"
YELLOW="\033[0;33m"
NC="\033[0m"

log() { echo -e "\n${YELLOW}[TEST] $1${NC}"; }

# Weryfikacja wstępna
if ! debox list | grep -q "$APP"; then
    echo "Aplikacja $APP musi być zainstalowana."
    exit 1
fi

# 1. Pobierz stan początkowy
OLD_CID=$(podman inspect $APP --format "{{.Id}}")
OLD_IID=$(podman inspect localhost/$APP:latest --format "{{.Id}}")

# --- CASE A: Zmiana Aliasów ---
log "Case A: Dodawanie aliasu (integration.aliases)"
debox configure $APP --key integration.aliases --map "ff-test=firefox-esr" > /dev/null
debox apply $APP > /dev/null

NEW_CID=$(podman inspect $APP --format "{{.Id}}")
NEW_IID=$(podman inspect localhost/$APP:latest --format "{{.Id}}")

if [ "$OLD_CID" == "$NEW_CID" ] && [ "$OLD_IID" == "$NEW_IID" ]; then
    echo -e "${GREEN}✅ PASS: Kontener i obraz zachowane (tylko reintegracja).${NC}"
else
    echo -e "${RED}❌ FAIL: Niepotrzebna rekreacja kontenera!${NC}"
    exit 1
fi

# --- CASE B: Zmiana Skip Categories ---
log "Case B: Dodawanie skip_categories"
debox configure $APP --key integration.skip_categories --add "Game" > /dev/null
debox apply $APP > /dev/null

NEW_CID=$(podman inspect $APP --format "{{.Id}}")
if [ "$OLD_CID" == "$NEW_CID" ]; then
    echo -e "${GREEN}✅ PASS: Kontener zachowany.${NC}"
else
    echo -e "${RED}❌ FAIL: Niepotrzebna rekreacja kontenera!${NC}"
    exit 1
fi

# Sprzątanie (przywracanie stanu)
log "Sprzątanie..."
debox configure $APP --key integration.aliases --unmap "ff-test" > /dev/null
debox configure $APP --key integration.skip_categories --remove "Game" > /dev/null
debox apply $APP > /dev/null