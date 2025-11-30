#!/bin/bash
# test_advanced_config.sh

APP="debox-firefox"
# Zakładamy, że wewnętrzna nazwa pliku .desktop dla Firefoxa to firefox-esr.desktop
INTERNAL_DESKTOP_FILE="firefox-esr.desktop"
HOST_DESKTOP_FILE="$HOME/.local/share/applications/${APP}_${INTERNAL_DESKTOP_FILE}"

# Kolory
GREEN="\033[0;32m"
RED="\033[0;31m"
YELLOW="\033[0;33m"
NC="\033[0m"

log_info() { echo -e "\n${YELLOW}--- $1 ---${NC}"; }

# Sprawdź czy aplikacja jest zainstalowana
if ! debox list | grep -q "$APP"; then
    echo -e "${RED}Błąd: Aplikacja $APP nie jest zainstalowana. Zainstaluj ją przed testem.${NC}"
    exit 1
fi

# --- TEST 1: Zmienne środowiskowe (runtime.environment) ---
log_info "TEST 1: Dodawanie zmiennej środowiskowej (Wymaga rekreacji kontenera)"

# 1. Pobierz ID kontenera przed zmianą
OLD_CID=$(podman inspect $APP --format "{{.Id}}")
echo "-> Stare ID kontenera: ${OLD_CID:0:12}"

# 2. Skonfiguruj zmienną
echo "-> Ustawianie zmiennej TEST_VAR=debox_rulez"
debox configure $APP --key runtime.environment --map TEST_VAR=debox_rulez > /dev/null

# 3. Aplikuj zmiany
debox apply $APP > /dev/null

# 4. Weryfikacja
# a) Czy zmienna jest w kontenerze?
if podman inspect $APP --format '{{.Config.Env}}' | grep -q "TEST_VAR=debox_rulez"; then
    echo -e "${GREEN}✅ Zmienna środowiskowa obecna w kontenerze.${NC}"
else
    echo -e "${RED}❌ BŁĄD: Zmienna środowiskowa nie została ustawiona!${NC}"
    exit 1
fi

# b) Czy kontener został odtworzony? (ID powinno być inne)
NEW_CID=$(podman inspect $APP --format "{{.Id}}")
echo "-> Nowe ID kontenera: ${NEW_CID:0:12}"

if [ "$OLD_CID" != "$NEW_CID" ]; then
    echo -e "${GREEN}✅ Kontener został poprawnie odtworzony (Recreated).${NC}"
else
    echo -e "${RED}❌ BŁĄD: Kontener NIE został odtworzony (ID jest to samo)!${NC}"
    exit 1
fi

# 5. Sprzątanie (usuń zmienną)
echo "-> Sprzątanie (usuwanie zmiennej)..."
debox configure $APP --key runtime.environment --unmap TEST_VAR > /dev/null
debox apply $APP > /dev/null


# --- TEST 2: Pomijanie nazw (integration.skip_names) ---
log_info "TEST 2: Ukrywanie ikony (Wymaga tylko reintegracji)"

# Upewnij się, że plik istnieje na początku
if [ ! -f "$HOST_DESKTOP_FILE" ]; then
    echo -e "${RED}Błąd wstępny: Plik $HOST_DESKTOP_FILE nie istnieje. Nie można przeprowadzić testu.${NC}"
    exit 1
fi

# 1. Pobierz ID kontenera przed zmianą
OLD_CID=$(podman inspect $APP --format "{{.Id}}")
echo "-> ID kontenera przed zmianą: ${OLD_CID:0:12}"

# 2. Dodaj nazwę do pomijania
echo "-> Dodawanie '$INTERNAL_DESKTOP_FILE' do skip_names"
debox configure $APP --key integration.skip_names --add "$INTERNAL_DESKTOP_FILE" > /dev/null

# 3. Aplikuj zmiany
debox apply $APP > /dev/null

# 4. Weryfikacja
# a) Czy plik .desktop zniknął?
if [ ! -f "$HOST_DESKTOP_FILE" ]; then
    echo -e "${GREEN}✅ Plik .desktop został poprawnie usunięty z hosta.${NC}"
else
    echo -e "${RED}❌ BŁĄD: Plik .desktop nadal istnieje!${NC}"
    exit 1
fi

# b) Czy kontener POZOSTAŁ ten sam? (Nie powinien być odtwarzany)
NEW_CID=$(podman inspect $APP --format "{{.Id}}")
echo "-> ID kontenera po zmianie:   ${NEW_CID:0:12}"

if [ "$OLD_CID" == "$NEW_CID" ]; then
    echo -e "${GREEN}✅ Kontener NIE został odtworzony (Poprawna optymalizacja).${NC}"
else
    echo -e "${RED}❌ OSTRZEŻENIE: Kontener został niepotrzebnie odtworzony (ID się zmieniło).${NC}"
    # To nie jest błąd krytyczny, ale oznacza brak optymalizacji w apply_cmd.py
fi

# 5. Sprzątanie (przywróć ikonę)
echo "-> Sprzątanie (przywracanie ikony)..."
debox configure $APP --key integration.skip_names --remove "$INTERNAL_DESKTOP_FILE" > /dev/null
debox apply $APP > /dev/null

if [ -f "$HOST_DESKTOP_FILE" ]; then
    echo -e "${GREEN}✅ Przywrócono stan początkowy.${NC}"
else
    echo -e "${RED}❌ Błąd przywracania stanu początkowego.${NC}"
fi

echo -e "\n${GREEN}=== Wszystkie testy zaawansowanej konfiguracji zakończone sukcesem! ===${NC}"