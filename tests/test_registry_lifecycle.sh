#!/bin/bash

set -e

# Kolory dla czytelności
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

# --- SPRZĄTANIE PRZED TESTEM ---
log "0. Sprzątanie środowiska..."
debox image rm ${IMAGE_NAME} > /dev/null 2>&1 || true
podman rmi ${LOCAL_TAG} > /dev/null 2>&1 || true
# Usuwamy też config dir, żeby symulować czysty start
rm -rf ~/.config/debox/images/${IMAGE_NAME}

# --- TEST 1: Build & Push ---
log "1. Budowanie obrazu i wypychanie do rejestru (debox image build)..."
debox image build ${CONFIG_FILE}
check_command

# Weryfikacja w liście
log "   Weryfikacja obecności na liście (debox image list)..."
if debox image list | grep -q "${IMAGE_NAME}:latest"; then
    echo -e "${GREEN}OK: Obraz widoczny w rejestrze.${NC}"
else
    echo -e "${RED}BŁĄD: Obraz nie pojawił się na liście!${NC}"
    exit 1
fi

# --- TEST 2: Symulacja utraty lokalnej (Local Delete) ---
log "2. Usuwanie obrazu z lokalnego cache Podmana..."
podman rmi ${LOCAL_TAG}
if ! podman images | grep -q "${LOCAL_TAG}"; then
    echo -e "${GREEN}OK: Obraz usunięty lokalnie.${NC}"
else
    echo -e "${RED}BŁĄD: Obraz nadal istnieje lokalnie!${NC}"
    exit 1
fi

# --- TEST 3: Przywracanie (Pull) ---
log "3. Przywracanie obrazu z rejestru (debox image pull)..."
debox image pull ${IMAGE_NAME}
check_command

# Weryfikacja czy wrócił do Podmana
if podman images | grep -q "${IMAGE_NAME}"; then
    echo -e "${GREEN}OK: Obraz przywrócony do cache Podmana.${NC}"
else
    echo -e "${RED}BŁĄD: Obraz nie został przywrócony!${NC}"
    exit 1
fi

# --- TEST 4: Usuwanie z rejestru (Remove) ---
log "4. Usuwanie obrazu z rejestru (debox image rm)..."
debox image rm ${IMAGE_NAME}
check_command

# Weryfikacja w liście (powinien być N/A lub zniknąć w zależności od implementacji)
log "   Weryfikacja usunięcia z listy..."
# Tutaj oczekujemy, że 'Backed Up' będzie 'No' lub obraz zniknie z listy (jeśli jest osierocony)
# Ponieważ to jest obraz bazowy (w ~/.config/debox/images), 'image list' powinien go pokazać jako N/A
OUTPUT=$(debox image list)
if echo "$OUTPUT" | grep "${IMAGE_NAME}" | grep -q "N/A"; then
     echo -e "${GREEN}OK: Obraz oznaczony jako usunięty (N/A).${NC}"
elif ! echo "$OUTPUT" | grep -q "${IMAGE_NAME}"; then
     # Jeśli usunęliśmy też folder configu (co robi remove_image_digest), to obraz zniknie z listy całkowicie
     # Sprawdźmy implementację. hash_utils.remove_image_digest usuwa tylko klucz z pliku.
     # Ale debox image list pokazuje obrazy na podstawie katalogu rejestru.
     # Po usunięciu manifestu, nazwa repozytorium zostaje w katalogu, ale nie ma tagów.
     # Nasza nowa logika listowania ukrywa puste repozytoria.
     echo -e "${GREEN}OK: Obraz zniknął z listy (brak tagów).${NC}"
else
    echo -e "${RED}BŁĄD: Obraz nadal widnieje jako dostępny!${NC}"
    echo "$OUTPUT"
    exit 1
fi

# --- TEST 5: Prune (Sprzątanie) ---
log "5. Czyszczenie rejestru (debox image prune)..."
# Uruchamiamy, żeby sprawdzić czy nie rzuca błędami
debox image prune
check_command

# --- SPRZĄTANIE KOŃCOWE ---
log "6. Sprzątanie po testach..."
podman rmi ${LOCAL_TAG} > /dev/null 2>&1 || true
rm -rf ~/.config/debox/images/${IMAGE_NAME} # Usuwamy ślad po obrazie bazowym

echo -e "\n${GREEN}✅ TESTY REJESTRU ZAKOŃCZONE SUKCESEM!${NC}"