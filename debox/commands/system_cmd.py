# debox/commands/system_cmd.py
"""
Handles setup of the debox system environment, primarily the local registry.
"""

import os
import sys
from pathlib import Path

from debox.core.log_utils import log_debug, log_info, log_error, console, run_step
from debox.core import podman_utils
from debox.core import global_config

REGISTRY_IMAGE = "docker.io/library/registry:2"

STORAGE_DIR = Path(os.path.expanduser("~/.local/share/debox/registry"))
CONF_DIR = Path(os.path.expanduser("~/.config/containers/registries.conf.d"))
CONF_FILE = CONF_DIR / "99-debox.conf"
REGISTRY_CONFIG_DIR = Path(os.path.expanduser("~/.config/debox/registry"))
REGISTRY_CONFIG_FILE = REGISTRY_CONFIG_DIR / "config.yml"

def setup_registry():
    """
    Initialize the local image registry environment.

    Creates the registry container, configures local storage, and updates Podman
    configuration to trust the local registry. Safe to run multiple times (idempotent).
    """
    registry_name = global_config.get_registry_name()
    registry_address = global_config.get_registry_address()
    registry_port = global_config._load_config().get('registry', 'port', fallback=global_config.DEFAULT_REGISTRY_PORT)
    
    console.print(f"--- Setting up local debox registry ({registry_name}) ---", style="bold")

    if os.geteuid() == 0:
        log_error("This command must be run as a regular user (rootless), not as root.", exit_program=True)
        return

    log_info(f"-> Ensuring global config exists at {global_config.GLOBAL_CONFIG_FILE}...")
    config = global_config._load_config()
    global_config.save_global_config(config)
    
    registry_address = global_config.get_registry_address()
    registry_port = config.get('registry', 'port', fallback=global_config.GLOBAL_REGISTRY_PORT)
    log_info(f"-> Using registry address: {registry_address}")

    with run_step(
        spinner_message="Creating required directories...",
        success_message="-> Directories prepared.",
        error_message="Failed to create directories"
    ):
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        CONF_DIR.mkdir(parents=True, exist_ok=True)
        REGISTRY_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    log_info(f"-> Writing Podman configuration to {CONF_FILE}...")
    podman_registry_conf = f"""
[[registry]]
  location = "{registry_address}"
  insecure = true
"""
    try:
        CONF_FILE.write_text(podman_registry_conf)
    except Exception as e:
        log_error(f"Failed to write Podman config: {e}", exit_program=True)

    log_info(f"-> Writing registry 'delete: enabled' config to {REGISTRY_CONFIG_FILE}...")
    registry_config_yaml = f"""
version: 0.1
log:
  level: info
storage:
  filesystem:
    rootdirectory: /var/lib/registry
  delete:
    enabled: true
http:
  addr: :{registry_port}
"""
    try:
        REGISTRY_CONFIG_FILE.write_text(registry_config_yaml)
    except Exception as e:
        log_error(f"Failed to write registry config: {e}", exit_program=True)

    with run_step(
        spinner_message=f"Pulling registry image '{REGISTRY_IMAGE}'...",
        success_message="-> Registry image is up to date.",
        error_message="Failed to pull registry image"
    ):
        podman_utils.run_command(["podman", "pull", REGISTRY_IMAGE])

    with run_step(
        spinner_message=f"Setting up container '{registry_name}'...",
        success_message="-> Registry container created.",
        error_message=f"Failed to create container '{registry_name}'"
    ):
        log_debug(f"-> Removing old container '{registry_name}' if it exists...")
        podman_utils.run_command(["podman", "stop", "--ignore", registry_name], check=False)
        podman_utils.run_command(["podman", "rm", "--ignore", registry_name], check=False)
        
        create_flags = [
            "--name", registry_name,
            "--label", "debox.managed=true",
            "-p", f"{registry_port}:{registry_port}",
            "-v", f"{STORAGE_DIR}:/var/lib/registry:Z", 
            "-v", f"{REGISTRY_CONFIG_FILE}:/etc/docker/registry/config.yml:ro",
            "--restart", "always",
            "-e", "REGISTRY_DELETE_ENABLED=true",
        ]
        
        podman_utils.create_container(registry_name, REGISTRY_IMAGE, create_flags)

    console.print(f"\n✅ Debox registry is configured. It will be started on demand.", style="bold green")
    console.print(f"   Registry Address: {registry_address}")
    console.print(f"   Storage Location: {STORAGE_DIR}")
    
    console.print(f"\nTip: To use this address manually, you can set an environment variable:")
    console.print(f"   export DEBOX_REGISTRY=\"{registry_address}\"")