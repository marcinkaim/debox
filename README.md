# Debox

**Debox** is a robust container manager for desktop applications on Debian, powered by **Podman**.

It allows you to run GUI (Firefox, VS Code, LibreOffice) and CLI (Midnight Commander) applications in isolated, rootless containers while maintaining seamless integration with your host desktop environment (launchers, icons, mime types).

## ✨ Key Features

- **Rootless & Secure**: Runs entirely in user space using Podman. No `sudo` required for running applications.
- **Desktop Integration**: Automatically exports `.desktop` files and icons to the host. Applications appear in your system menu like native apps.
- **Declarative Configuration**: Define your applications using simple, reusable YAML files.
- **Local Registry & Backup**: Built-in local registry to store your images. Automatically backs up images and restores them if they are accidentally deleted.
- **Layered Images**: Support for shared base images to save disk space and speed up builds.
- **Hardware Acceleration**: Out-of-the-box support for GPU acceleration, PulseAudio/PipeWire sound, and Webcam access.
- **Self-Healing**: Automatically detects missing containers or images and restores them from the registry on the fly.

## 🛠️ Building from Source

To install Debox, you first need to build the Debian package from the source code.

### Build Prerequisites

- **Debian 13 (Trixie)** or newer.
- **Pandoc** (required for generating man pages).
- **Git**.

Install build dependencies:

```bash
sudo apt install git pandoc dpkg-dev
```

### Build Instructions

Clone the repository:

```bash
git clone [https://github.com/marcinkaim/debox.git](https://github.com/marcinkaim/debox.git)
cd debox
```

Run the build script:

```bash
./build_deb.sh
```

Upon success, the package `debox_0.5.4-1_all.deb` will be created in the project root directory.

## 🚀 Installation

### Prerequisites

- **Podman** installed:

```bash
sudo apt install podman
```

### Installing the Package

Once you have built the package (or downloaded it from **Releases**), install it using `apt`:

```bash
# Install the package (resolves Python dependencies automatically)
sudo apt install ./debox_0.5.4-1_all.deb
```

### Verification

After installation, restart your terminal to load autocompletion settings, then verify:
```bash
debox --help
man debox
```

## 🏁 Quick Start

### 1. Initialize the Environment

Before installing applications, you need to set up the local image registry. This is a one-time operation.
```bash
debox system setup-registry
```

### 2. Build a Base Image

Create a base image that holds common dependencies (locales, fonts, utils). Save this as `base.yml`:
```yaml
version: 1
image_name: "debox-base"
image:
  base: "debian:latest"
  packages: ["python3", "locales", "sudo", "fonts-noto-core", "libpulse0"]
```

Build it:
```bash
debox image build base.yml
```

### 3. Install an Application

Create a config file for an application, e.g., `firefox.yml`:

```bash
version: 1
app_name: "Firefox"
container_name: "debox-firefox"
image:
  base: "localhost/debox-base:latest"
  packages: ["firefox-esr"]
integration:
  desktop_integration: true
permissions:
  network: true
  gpu: true
  sound: true
```

Install it:

```bash
debox install --config firefox.yml
```

### 4. Run

You can now find "Firefox" in your system menu, or run it via terminal:

```bash
debox run debox-firefox
```

## 📖 Usage Guide

### Managing Applications

- List applications: `debox list`
- Remove an application:
```bash
debox remove debox-firefox
# Use --purge to remove config and registry backup
debox remove debox-firefox --purge
```
- Reinstall (Force rebuild): `debox reinstall debox-firefox`
- Upgrade (In-place update): Updates packages inside the container without rebuilding the image.
```bash
debox upgrade debox-firefox
```
- Repair (Fix container): `debox repair debox-firefox`

### Configuration Management

You can modify settings without editing YAML files manually.

1. Change a setting:
```bash
debox configure debox-firefox --key permissions.network --set false
```

2. Apply changes:
Debox intelligently decides whether to rebuild the image, recreate the container, or just update desktop integration.
```bash
debox apply debox-firefox
```

### Image Management

Debox uses a local registry (localhost:5000) to backup your images.

- **List backed-up images:** `debox image list`
- **Clean up storage:** `debox image prune`
- **Restore deleted app:** `debox image restore debox-firefox`
- **Pull image to cache:** `debox image pull debox-firefox`

## ⚙️ Configuration Reference (YAML)

A valid `config.yml` consists of the following sections:

### Metadata

- `app_name`: Human-readable name.
- `container_name`: Unique ID for Podman.

`image`
Defines how the image is built.

- `base`: Source image (e.g., debian:latest or localhost/debox-base:latest).
- `packages`: List of apt packages to install.
- `local_debs`: List of paths to local .deb files to install.
- `repositories`: List of external APT repositories.
- `debian_components`: List of Debian components (e.g. contrib, non-free).

`storage`
Defines volume mounts.

- volumes: List of mounts in format host_path:container_path or host_path:container_path:ro.

`runtime`

- default_exec: Command to run by default.
- interactive: Set to true for CLI apps (mc, htop) to enable TTY.
- environment: Dictionary of environment variables.
- prepend_exec_args: List of flags to prepend to the command.

`integration`

- desktop_integration: Enable/disable .desktop file export.
- aliases: Map of command aliases to create on host.
- skip_names: List of .desktop files to ignore (prevent menu clutter).
- skip_categories: List of desktop categories to ignore.

`permissions`

Booleans to enable/disable access: `network`, `gpu`, `sound`, `webcam`, `microphone`, `bluetooth`, `printers`, `host_opener`.

`security`
Controls cryptographic identity and isolation.

- `gpg_key_id`: The ID of a GPG key residing on the host. If specified, this key (public and secret) is exported to a strictly isolated temporary keyring mounted at `~/.gnupg` inside the container.

`lifecycle`
Controls scripts executed at specific points in the container's lifecycle.

- `post_install`: A shell script (Bash) to be executed inside the container immediately after it is created and desktop integration is applied. Useful for instance-specific configuration (e.g., git config, installing extensions).

### Examples

VS Code with automated Git identity setup:

```yaml
version: 1
app_name: "VS Code (Project X)"
container_name: "debox-vscode-projx"
image:
  base: "localhost:5000/debox-base-vscode:latest"
security:
  gpg_key_id: "0123456789ABCDEF..."
lifecycle:
  post_install: |
    git config --global user.name "User1"
    git config --global user.email "user1@example.com"
    # DEBOX_GPG_KEY_ID is automatically injected if security.gpg_key_id is set
    if [ -n "$DEBOX_GPG_KEY_ID" ]; then
      git config --global user.signingkey "$DEBOX_GPG_KEY_ID"
      git config --global commit.gpgsign true
    fi
```

## ⚖️ License

MIT License. See LICENSE file for details.

