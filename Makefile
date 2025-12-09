# Makefile for Debox
# Wrapper around build and release scripts

.PHONY: all build push release clean install

APP_NAME = debox
BUILD_DIR = build
SCRIPTS_DIR = scripts

# Default target
all: build

# 1. Build the package (includes auto-bump and signing)
build:
	@echo "--- 🔨 Building Package ---"
	@bash ./build_deb.sh

# 2. Sync git repository (push commits and tags)
push:
	@echo "--- ☁️  Pushing to GitHub ---"
	@bash $(SCRIPTS_DIR)/push_repo.sh

# 3. Create GitHub Release and upload assets
release:
	@echo "--- 🚀 Publishing Release ---"
	@bash $(SCRIPTS_DIR)/release_github.sh

# Chain: Build -> Push -> Release
publish: build push release

# Clean build artifacts
clean:
	@echo "--- 🧹 Cleaning up ---"
	@rm -rf $(BUILD_DIR)
	@rm -f *.deb *.asc
	@echo "Done."

# Local installation for testing
install:
	@echo "--- 📦 Installing locally ---"
	@sudo apt install ./$(APP_NAME)_*_all.deb