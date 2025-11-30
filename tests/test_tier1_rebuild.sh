#!/bin/bash
set -e

APP="debox-firefox"
GREEN="\033[0;32m"
RED="\033[0;31m"
YELLOW="\033[0;33m"
NC="\033[0m"

log() { echo -e "\n${YELLOW}[TEST] $1${NC}"; }

# 1. Stan początkowy
OLD_CID=$(podman inspect $APP --format "{{.Id}}")
OLD_IID=$(podman inspect localhost/$APP:latest --format "{{.Id}}")

# --- CASE A: Dodanie pakietu (image.packages) ---
log "Case A: Dodanie pakietu do image.packages (Wymaga przebudowy)"
# Używamy małego pakietu 'tree' dla szybkości
debox configure $APP --key image.packages --add "tree" > /dev/null
debox apply $APP > /dev/null

NEW_CID=$(podman inspect $APP --format "{{.Id}}")
NEW_IID=$(podman inspect localhost/$APP:latest --format "{{.Id}}")

# Weryfikacja Obrazu
if [ "$OLD_IID" != "$NEW_IID" ]; then
    echo -e "${GREEN}✅ PASS: Obraz został przebudowany.${NC}"
else
    echo -e "${RED}❌ FAIL: Obraz NIE został przebudowany!${NC}"
    exit 1
fi

# Weryfikacja Kontenera
if [ "$OLD_CID" != "$NEW_CID" ]; then
    echo -e "${GREEN}✅ PASS: Kontener został odtworzony (wymagane po przebudowie).${NC}"
else
    echo -e "${RED}❌ FAIL: Kontener NIE został odtworzony!${NC}"
    exit 1
fi

# Sprzątanie
log "Sprzątanie..."
debox configure $APP --key image.packages --remove "tree" > /dev/null
debox apply $APP > /dev/null