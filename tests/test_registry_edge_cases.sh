#!/bin/bash

set -e

# --- Konfiguracja ---
IMAGE_NAME="debox-fail-test"
CONFIG_FILE="tests/test-image-fail.yml"
REGISTRY_CONTAINER="debox-registry"

# Kolory
GREEN="\033[0;32m"
RED="\033[0;31m"
YELLOW="\033[0;33m"
NC="\033[0m"

log() { echo -e "\n${YELLOW}[EDGE-TEST] $1${NC}"; }

# Helpery asercji
assert_fail() {
    if "$@"; then
        echo -e "${RED}BŁĄD: Komenda powinna się nie udać, a zakończyła się sukcesem!${NC}"
        exit 1
    else
        echo -e "${GREEN}OK: Komenda poprawnie zgłosiła błąd.${NC}"
    fi
}

assert_pass() {
    if "$@"; then
        echo -e "${GREEN}OK: Komenda zakończona sukcesem.${NC}"
    else
        echo -e "${RED}BŁĄD: Komenda powinna się udać, a wystąpił błąd!${NC}"
        exit 1
    fi
}

# --- PRZYGOTOWANIE ---
# Tworzymy tymczasowy config
echo "version: 1
image_name: \"$IMAGE_NAME\"
image:
  base: \"debian:stable-slim\"
  packages: []" > $CONFIG_FILE

# Sprzątanie
debox image rm $IMAGE_NAME > /dev/null 2>&1 || true
rm -rf ~/.config/debox/images/$IMAGE_NAME


# === SCENARIUSZ 1: Operacje na nieistniejących zasobach ===
log "1. Próba wypchnięcia (push) nieistniejącego obrazu..."
# Nie zbudowaliśmy go jeszcze, więc push musi zawieść
assert_fail debox image push $IMAGE_NAME

log "2. Próba pobrania (pull) nieistniejącego obrazu..."
assert_fail debox image pull "debox-non-existent-image"

log "3. Próba usunięcia (rm) nieistniejącego obrazu..."
# To powinno zawieść, bo nie ma digestu ani obrazu
assert_fail debox image rm "debox-non-existent-image"


# === SCENARIUSZ 2: Samonaprawianie infrastruktury (Registry Down) ===
log "4. Test Self-Healing: Zatrzymanie kontenera rejestru..."
podman stop $REGISTRY_CONTAINER
# Upewnij się, że jest zatrzymany
if podman ps --filter name=$REGISTRY_CONTAINER --format "{{.Status}}" | grep -q "Up"; then
    echo "Błąd: Nie udało się zatrzymać rejestru."
    exit 1
fi

log "   Próba wylistowania obrazów (powinna uruchomić rejestr)..."
# To polecenie powinno wykryć, że rejestr leży, uruchomić go i zwrócić wynik
assert_pass debox image list

# Weryfikacja czy wstał
if podman ps --filter name=$REGISTRY_CONTAINER --format "{{.Status}}" | grep -q "Up"; then
    echo -e "${GREEN}OK: Rejestr został automatycznie uruchomiony.${NC}"
else
    echo -e "${RED}BŁĄD: Rejestr nie wstał!${NC}"
    exit 1
fi


# === SCENARIUSZ 3: Desynchronizacja (Ghost Image) ===
# Symulujemy sytuację: Debox myśli, że obraz jest (ma digest), ale w rejestrze go nie ma.
log "5. Przygotowanie: Budowanie poprawnego obrazu..."
debox image build $CONFIG_FILE > /dev/null

log "   Sabotaż: Ręczne usunięcie obrazu z rejestru (bez wiedzy Deboxa)..."
# Pobieramy digest, żeby go usunąć "za plecami" deboxa
DIGEST=$(curl -s -H "Accept: application/vnd.docker.distribution.manifest.v2+json" http://localhost:5000/v2/$IMAGE_NAME/manifests/latest | grep Docker-Content-Digest | awk '{print $2}' | tr -d '\r')
# Usuwamy manifest ręcznie przez API
curl -s -X DELETE http://localhost:5000/v2/$IMAGE_NAME/manifests/$DIGEST > /dev/null

log "   Weryfikacja zachowania 'debox image rm' na nieistniejącym zdalnie obrazie..."
# Debox ma zapisany digest w pliku. Spróbuje go usunąć. Rejestr zwróci 404.
# Oczekujemy, że debox to obsłuży (wyświetli ostrzeżenie), ale POSPRZĄTA plik lokalny i zakończy sukcesem.
assert_pass debox image rm $IMAGE_NAME

# Sprawdź, czy plik digestu został usunięty
if [ -f ~/.config/debox/images/$IMAGE_NAME/.last_applied_state.json ]; then
     # Plik może istnieć, ale nie powinien mieć klucza registry_digest.
     # Dla uproszczenia: sprawdźmy czy ponowne rm rzuci błąd "No saved digest"
     log "   Sprawdzenie czy lokalny ślad został usunięty..."
     assert_fail debox image rm $IMAGE_NAME
else
     echo -e "${GREEN}OK: Lokalny ślad usunięty.${NC}"
fi


# === SCENARIUSZ 4: Brak Digestu (Fallback do API) ===
# Symulujemy sytuację: Obraz jest w rejestrze, ale Debox zgubił plik z digestem.
log "6. Przygotowanie: Ponowne zbudowanie obrazu..."
debox image build $CONFIG_FILE > /dev/null

log "   Sabotaż: Usunięcie lokalnego pliku stanu..."
rm ~/.config/debox/images/$IMAGE_NAME/.last_applied_state.json

log "   Weryfikacja 'debox image rm' (Fallback do API)..."
# Debox nie znajdzie digestu w pliku. Powinien zapytać API, pobrać digest i usunąć obraz.
assert_pass debox image rm $IMAGE_NAME

# Sprawdź czy faktycznie usunięto z rejestru (API powinno zwrócić 404)
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/v2/$IMAGE_NAME/manifests/latest)
if [ "$HTTP_CODE" -eq 404 ]; then
    echo -e "${GREEN}OK: Obraz faktycznie usunięty z rejestru.${NC}"
else
    echo -e "${RED}BŁĄD: Obraz nadal istnieje w rejestrze (kod $HTTP_CODE)!${NC}"
    exit 1
fi


# --- SPRZĄTANIE KOŃCOWE ---
rm $CONFIG_FILE
rm -rf ~/.config/debox/images/$IMAGE_NAME
podman rmi localhost/$IMAGE_NAME:latest > /dev/null 2>&1 || true

echo -e "\n${GREEN}=== WSZYSTKIE TESTY GRANICZNE ZAKOŃCZONE SUKCESEM ===${NC}"