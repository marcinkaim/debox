---
title: DEBOX.YML
section: 5
header: Debox Configuration File
footer: Debox 0.1.0
date: December 2025
...

# NAME

debox.yml - Configuration file format for Debox applications.

# DESCRIPTION

The debox configuration file is a YAML document that defines how a containerized application should be built, run, and integrated with the host system.

By convention, application configurations are stored in ~/.config/debox/apps/<container_name>/config.yml.

# STRUCTURE

The configuration file consists of several top-level sections.

## Metadata

**version** (integer, required)
:   The version of the configuration schema. Currently 1.

**app_name** (string, required)
:   The human-readable name of the application (e.g., "Firefox ESR"). Used for menu entries.

**container_name** (string, required)
:   The unique identifier for the container (e.g., "debox-firefox"). Must be unique across all installed applications.

## Image Section (image)

Defines how the container image is built.

**base** (string, required)
:   The base image to use. Can be a public image (e.g., debian:latest) or a local base image (e.g., localhost/debox-base:latest).

**debian_components** (list of strings, optional)
:   List of Debian repository components to enable (e.g., ["contrib", "non-free", "non-free-firmware"]). Only used if the base image is a standard Debian image.

**apt_target_release** (string, optional)
:   The default target release for apt-get install (e.g., trixie-backports). Useful for pinning versions.

**repositories** (list of objects, optional)
:   List of external APT repositories to add.

* **repo_string** (string): The full deb line (e.g., `deb https://...`).
* **key_url** (string, optional): URL to the GPG key.
* **key_path** (string, optional): Path where the key should be saved inside the image.
* **list_filename** (string, optional): Name of the list file in `/etc/apt/sources.list.d/`.


**local_debs** (list of strings, optional)
:   List of paths to local .deb files on the host. These files will be copied into the image and installed. Paths can use ~ for the home directory.

**packages** (list of strings, optional)
:   List of system packages to install via apt-get.

## Storage Section (storage)

Defines persistent storage and volume mounts.

**volumes** (list of strings, optional)
:   List of volumes to mount. Format: host_path:container_path[:options].

* `~/Documents:/home/user/Documents` (Read-Write)
* `/tmp/.X11-unix:/tmp/.X11-unix:ro` (Read-Only)


## Runtime Section (runtime)

Defines how the application is executed.

**default_exec** (string, required)
:   The command to run when debox run <name> is called without arguments.

**interactive** (boolean, optional, default: false)
:   If true, debox run will allocate a TTY (-it) and pass the TERM variable. Required for CLI tools like mc or htop.

**environment** (dictionary, optional)
:   Key-value pairs of environment variables to set inside the container.

**prepend_exec_args** (list of strings, optional)
:   List of arguments prepended to the command. Useful for flags like --ozone-platform=wayland.

## Integration Section (integration)

Controls desktop environment integration.

**desktop_integration** (boolean, optional, default: true)
:   If true, .desktop files and icons will be exported to the host.

**aliases** (dictionary, optional)
:   Map of command aliases to create in ~/.local/bin/. Key is the command inside container, value is the alias name on host.
Example: `{"code": "code-debox"}`.

**skip_categories** (list of strings, optional)
:   List of desktop categories to ignore during export (e.g., ["Utility"]).

**skip_names** (list of strings, optional)
:   List of specific .desktop filenames or app names to ignore during export (e.g., ["org.gnome.Settings.desktop"]).

## Permissions Section (permissions)

Controls container security and hardware access.

**network** (boolean, default: true)
:   Enable network access.

**gpu** (boolean, default: true)
:   Enable GPU acceleration (/dev/dri).

**sound** (boolean, default: true)
:   Enable sound (PulseAudio/PipeWire socket).

**webcam** (boolean, default: false)
:   Enable access to video devices (/dev/video*).

**microphone** (boolean, default: false)
:   Enable microphone access.

**bluetooth** (boolean, default: false)
:   Enable Bluetooth access.

**printers** (boolean, default: false)
:   Enable access to CUPS socket.

**system_dbus** (boolean, default: true)
:   Mount the system D-Bus socket (read-only).

**host_opener** (boolean, default: false)
:   Allow the container to open URLs on the host system using the default browser.

**devices** (list of strings, optional)
:   List of specific device paths to pass to the container (e.g., ["/dev/bus/usb/001/002"]).

# EXAMPLES

A simple CLI tool:

```yaml
version: 1
app_name: "Midnight Commander"
container_name: "debox-mc"
image:
  base: "localhost/debox-base-minimal:latest"
  packages: ["mc"]
storage:
  volumes: ["~:/home/marcin/HostHome"]
runtime:
  default_exec: "mc"
  interactive: true
integration:
  desktop_integration: false
  aliases: {"mc": "mc-debox"}
```

# SEE ALSO

debox(1)
