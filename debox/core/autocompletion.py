# debox/core/autocompletion.py
"""
Provides dynamic autocompletion functions for Typer.
"""

import yaml
from typing import List

from debox.core import config_utils

def complete_container_names() -> List[str]:
    """
    Returns a list of all installed container names
    (e.g., 'debox-firefox', 'debox-vscode') for autocompletion.
    """
    container_names = []
    if not config_utils.DEBOX_APPS_DIR.is_dir():
        return []  # Return an empty list if the directory doesn't exist
    
    for app_dir in config_utils.DEBOX_APPS_DIR.iterdir():
        if app_dir.is_dir():
            config_path = app_dir / "config.yml"
            if config_path.is_file():
                try:
                    # Quickly load YAML to find only the 'container_name'
                    with open(config_path, 'r') as f:
                        config = yaml.safe_load(f)
                        if config and 'container_name' in config:
                            container_names.append(config['container_name'])
                except Exception:
                    continue  # Skip corrupted config files
    return container_names

VALID_CONFIG_KEYS = [
    "image.base", "image.debian_components", "image.apt_target_release",
    "image.repositories", "image.packages",
    "storage.volumes",
    "runtime.default_exec", "runtime.prepend_exec_args",
    "runtime.environment",
    "integration.desktop_integration", "integration.skip_categories",
    "integration.aliases",
    "permissions.network", "permissions.bluetooth", "permissions.gpu",
    "permissions.sound", "permissions.webcam", "permissions.microphone",
    "permissions.printers", "permissions.system_dbus", "permissions.host_opener",
    "permissions.devices",
]

BOOLEAN_KEYS = [
    "integration.desktop_integration",
    "permissions.network", "permissions.bluetooth", "permissions.gpu",
    "permissions.sound", "permissions.webcam", "permissions.microphone",
    "permissions.printers", "permissions.system_dbus", "permissions.host_opener",
    "runtime.interactive",
]

LIST_KEYS = [
    "image.debian_components", "image.repositories", "image.packages",
    "storage.volumes", "runtime.prepend_exec_args",
    "integration.skip_categories", "permissions.devices",
]

MAP_KEYS = [
    "integration.aliases",
    "runtime.environment",
]
    
def complete_config_keys(incomplete: str) -> List[str]:
    """Suggests only keys (without ':')"""
    return [key for key in VALID_CONFIG_KEYS if key.startswith(incomplete)]

def complete_boolean_values(incomplete: str) -> List[str]:
    """Suggests only 'true' or 'false'."""
    if "true".startswith(incomplete):
        return ["true"]
    if "false".startswith(incomplete):
        return ["false"]
    return ["true", "false"]
