#!/bin/bash
# test_config_changes.sh

# Konfiguracja testu
APP="debox-firefox"
CONFIG_KEY="permissions.network"

# Kolory
GREEN="\033[0;32m"
RED="\033[0;31m"
NC="\033[0m"

echo "--- TEST 1: Zmiana konfiguracji (enable network) ---"

# 1. Ustaw na TRUE
echo "-> Ustawianie $CONFIG_KEY = true"
# Używamy flagi --verbose, aby widzieć błędy, ale przekierowujemy stdout
debox configure $APP --key $CONFIG_KEY --set true > /dev/null
debox apply $APP > /dev/null

# Weryfikacja JSON: Szukamy .HostConfig.NetworkMode
NET_MODE=$(podman inspect $APP --format '{{.HostConfig.NetworkMode}}')

if [ "$NET_MODE" == "default" ] || [ "$NET_MODE" == "slirp4netns" ] || [ "$NET_MODE" == "pasta" ] || [ -z "$NET_MODE" ]; then
    # Pusty NetworkMode lub "default" oznacza włączoną sieć w Podmanie rootless
    echo -e "${GREEN}✅ Weryfikacja 1: Kontener ma sieć (Mode: '$NET_MODE').${NC}"
else
    echo -e "${RED}❌ BŁĄD 1: Kontener nie ma sieci (Mode: '$NET_MODE')!${NC}"
    exit 1
fi

echo -e "\n--- TEST 2: Zmiana konfiguracji (disable network) ---"

# 2. Ustaw na FALSE
echo "-> Ustawianie $CONFIG_KEY = false"
debox configure $APP --key $CONFIG_KEY --set false > /dev/null
debox apply $APP > /dev/null

# Weryfikacja JSON
NET_MODE=$(podman inspect $APP --format '{{.HostConfig.NetworkMode}}')

if [ "$NET_MODE" == "none" ]; then
    echo -e "${GREEN}✅ Weryfikacja 2: Kontener nie ma sieci (Mode: 'none').${NC}"
else
    echo -e "${RED}❌ BŁĄD 2: Kontener nadal ma sieć (Mode: '$NET_MODE')!${NC}"
    exit 1
fi

echo -e "\n--- TEST 3: Komenda 'debox network allow' ---"

debox network allow $APP > /dev/null
NET_MODE=$(podman inspect $APP --format '{{.HostConfig.NetworkMode}}')

if [ "$NET_MODE" != "none" ]; then
    echo -e "${GREEN}✅ Weryfikacja 3: Sieć włączona przez 'network allow'.${NC}"
else
    echo -e "${RED}❌ BŁĄD 3: 'network allow' nie zadziałało.${NC}"
    exit 1
fi

echo -e "\n--- TEST 4: Komenda 'debox network deny' ---"

debox network deny $APP > /dev/null
NET_MODE=$(podman inspect $APP --format '{{.HostConfig.NetworkMode}}')

if [ "$NET_MODE" == "none" ]; then
    echo -e "${GREEN}✅ Weryfikacja 4: Sieć wyłączona przez 'network deny'.${NC}"
else
    echo -e "${RED}❌ BŁĄD 4: 'network deny' nie zadziałało.${NC}"
    exit 1
fi

echo -e "\n--- TEST 5: Idempotentność (No changes needed) ---"
echo "-> Uruchamianie 'debox apply' bez zmian..."
OUTPUT=$(debox apply $APP 2>&1) # Przechwytujemy też stderr
if echo "$OUTPUT" | grep -q "No changes needed"; then
    echo -e "${GREEN}✅ Weryfikacja 5: Poprawnie wykryto brak zmian.${NC}"
else
    echo -e "${RED}❌ BŁĄD 5: 'apply' wykonało akcję mimo braku zmian.${NC}"
    # echo "DEBUG OUTPUT: $OUTPUT"
    exit 1
fi

echo -e "\n${GREEN}--- Wszystkie testy zakończone sukcesem! ---${NC}"