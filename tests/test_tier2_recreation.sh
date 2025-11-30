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

# --- CASE A: Zmiana Runtime (Zmienna środowiskowa) ---
log "Case A: Zmiana runtime.environment"
debox configure $APP --key runtime.environment --map "TEST_ENV=1" > /dev/null
debox apply $APP > /dev/null

NEW_CID=$(podman inspect $APP --format "{{.Id}}")
NEW_IID=$(podman inspect localhost/$APP:latest --format "{{.Id}}")

if [ "$OLD_CID" != "$NEW_CID" ]; then
    echo -e "${GREEN}✅ PASS: Kontener odtworzony (prawidłowo).${NC}"
else
    echo -e "${RED}❌ FAIL: Kontener NIE został odtworzony!${NC}"
    exit 1
fi

if [ "$OLD_IID" == "$NEW_IID" ]; then
    echo -e "${GREEN}✅ PASS: Obraz zachowany (optymalizacja).${NC}"
else
    echo -e "${RED}❌ FAIL: Obraz niepotrzebnie przebudowany!${NC}"
    exit 1
fi

# Aktualizuj 'stary' CID do bieżącego dla następnego testu
OLD_CID=$NEW_CID

# --- CASE B: Zmiana Permissions (Network) ---
log "Case B: Zmiana permissions.network"
# Zmieniamy na przeciwny (jeśli było true to false, itd.)
CURRENT_NET=$(podman inspect $APP --format '{{.HostConfig.NetworkMode}}')
if [ "$CURRENT_NET" == "none" ]; then TARGET="true"; else TARGET="false"; fi

debox configure $APP --key permissions.network --set $TARGET > /dev/null
debox apply $APP > /dev/null

NEW_CID=$(podman inspect $APP --format "{{.Id}}")
if [ "$OLD_CID" != "$NEW_CID" ]; then
    echo -e "${GREEN}✅ PASS: Kontener odtworzony (zmiana uprawnień).${NC}"
else
    echo -e "${RED}❌ FAIL: Kontener NIE został odtworzony!${NC}"
    exit 1
fi
OLD_CID=$NEW_CID

# --- CASE C: Krytyczna Integracja (Desktop Integration) ---
log "Case C: Zmiana integration.desktop_integration (Test 'Critical Integration Hash')"
# To jest w sekcji 'integration', ale powinno wymusić rekreację (bo zmienia montowania)
debox configure $APP --key integration.desktop_integration --set false > /dev/null
debox apply $APP > /dev/null

NEW_CID=$(podman inspect $APP --format "{{.Id}}")
if [ "$OLD_CID" != "$NEW_CID" ]; then
    echo -e "${GREEN}✅ PASS: Kontener odtworzony (zmiana krytycznej integracji).${NC}"
else
    echo -e "${RED}❌ FAIL: Kontener NIE został odtworzony, a powinien!${NC}"
    echo "   Sprawdź logikę 'integration_critical' w hash_utils.py"
    exit 1
fi

# Sprzątanie
log "Sprzątanie..."
debox configure $APP --key runtime.environment --unmap "TEST_ENV" > /dev/null
debox configure $APP --key permissions.network --set true > /dev/null
debox configure $APP --key integration.desktop_integration --set true > /dev/null
debox apply $APP > /dev/null