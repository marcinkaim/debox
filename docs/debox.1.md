---
title: DEBOX
section: 1
header: Debox Manual
footer: Debox 0.1.0
date: December 2025
...

# NAME

debox - Container manager for desktop applications on Debian, powered by Podman.

# SYNOPSIS

debox [--verbose | -v] [--quiet | -q] COMMAND [ARGS]...

# DESCRIPTION

debox is a tool designed to manage desktop applications running inside isolated, rootless Podman containers. It provides seamless integration with the host desktop environment (icons, .desktop files, mime types) while keeping the host system clean and secure.

It manages the entire lifecycle of an application: building images, creating containers, handling updates, and managing configuration.

# OPTIONS

**-v**, **--verbose**
:   Enable verbose output. Shows detailed technical logs, Podman commands, and debugging information.

**-q**, **--quiet**
:   Suppress all output except for errors and warnings. Useful for scripting.

**--install-completion**
:   Install completion for the current shell.

**--show-completion**
:   Show completion for the current shell, to copy it or customize the installation.

**--help**
:   Show this message and exit.

# COMMANDS

## Core Commands

**install** [CONTAINER_NAME] [--config FILE]
:   Install a new application or repair an existing one.
If CONTAINER_NAME is provided without --config, it attempts to reinstall/repair from the existing configuration.
If --config is provided, it performs a fresh installation using that file.

**remove** CONTAINER_NAME [--purge]
:   Remove an application and its artifacts (container, local image, desktop integration).
By default, the configuration directory and isolated home directory are preserved.
Use --purge to delete everything, including user data and the backup image in the registry.

**list**
:   List all installed applications, their container status, configuration status, and base image.

**run** CONTAINER_NAME [ARGS]...
:   Launch an application inside its container.
If ARGS are provided (after a -- separator), they are executed inside the container.
Otherwise, the default_exec command defined in the configuration is used.
This command automatically handles starting/stopping the container and TTY allocation.

**upgrade** CONTAINER_NAME
:   Upgrade system packages (apt-get upgrade) inside the container without rebuilding the image from scratch. Commits changes and updates the registry backup.

**reinstall** CONTAINER_NAME [--config FILE]
:   Force a full clean re-installation. Removes the existing container and image, then rebuilds everything from the configuration file. Preserves user data.

**repair** CONTAINER_NAME
:   Quickly repair an installation by recreating the container instance and re-applying desktop integration. Does not rebuild the image.

## Configuration Commands

**configure** CONTAINER_NAME --key KEY [ACTION_OPTION VALUE]
:   Modify the configuration for an installed application. Changes are staged and require debox apply to take effect.

Options:

**--key**, **-k** *KEY*
:   The configuration key to modify (e.g., `permissions.network`, `image.packages`).

**--set**, **-s** *VALUE*
:   Set a simple value (string or boolean).

**--add** *VALUE*
:   Add a value to a list.

**--remove**, **-r** *VALUE*
:   Remove a value from a list.

**--map**, **-m** *KEY=VALUE*
:   Set a key-value pair in a dictionary/map.

**--unmap**, **-u** *KEY*
:   Remove a key from a dictionary/map.


**apply** CONTAINER_NAME
:   Apply pending configuration changes made by configure. Automatically detects what needs to be done (rebuild image, recreate container, or just re-integrate).

## Network Commands

**network** allow CONTAINER_NAME
:   Enable network access for the container (requires container recreation).

**network** deny CONTAINER_NAME
:   Disable network access for the container (requires container recreation).

## Image & Registry Commands

**image** list
:   List images stored in the local backup registry and their association with installed apps.

**image** push CONTAINER_NAME
:   Manually backup a local application image to the internal registry.

**image** pull IMAGE_NAME
:   Restore an image from the internal registry to the local Podman cache.

**image** rm IMAGE_NAME [tag]
:   Permanently delete an image from the internal registry.

**image** prune [--dry-run]
:   Run Garbage Collection on the local registry to free up disk space. Removes unreferenced blobs.

**image** restore [--all | CONTAINER_NAME]
:   Restore missing containers/images from the registry based on local configuration.

**image** build CONFIG_FILE
:   Build a shared base image from a configuration file and push it to the registry.

## System Commands

**system** setup-registry
:   Initialize or repair the local image registry environment. Creates the registry container and configures Podman.

# FILES

~/.config/debox/apps/
:   Directory containing configuration and state for installed applications.

~/.config/debox/images/
:   Directory containing state for base images.

~/.config/debox/registry/
:   Configuration for the internal registry container.

~/.local/share/debox/homes/
:   Isolated home directories for applications.

~/.local/share/debox/registry/
:   Storage volume for the internal registry.

# EXAMPLES

Install Firefox from a config file:

```bash
debox install --config examples/firefox.yml
```

Run Firefox:

```bash
debox run debox-firefox
```

Disable network access for an app:

```bash
debox network deny debox-firefox
```

Add a package to an existing app:

```bash
debox configure debox-firefox --key image.packages --add htop
debox apply debox-firefox
```

Reinstall VS Code using a fresh config:

```bash
debox reinstall debox-vscode --config new-config.yml
```

# AUTHOR

Marcin Kaim

# LICENSE

MIT License
