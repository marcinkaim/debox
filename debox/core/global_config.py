# debox/core/global_config.py
"""
Manages the global debox configuration file (e.g., ~/.config/debox/debox.conf).
"""

import os
import configparser
from pathlib import Path

# --- Constants ---
GLOBAL_CONFIG_DIR = Path(os.path.expanduser("~/.config/debox"))
GLOBAL_CONFIG_FILE = GLOBAL_CONFIG_DIR / "debox.conf"

# --- Registry Constants ---
# These are the defaults that will be written to the config file
DEFAULT_REGISTRY_HOST = "localhost"
DEFAULT_REGISTRY_PORT = "5000"
DEFAULT_REGISTRY_NAME = "debox-registry"
# --- End Registry Constants ---

def _load_config() -> configparser.ConfigParser:
    """Loads the config file, applying defaults if it doesn't exist."""
    config = configparser.ConfigParser()
    
    config['registry'] = {
        'host': DEFAULT_REGISTRY_HOST,
        'port': DEFAULT_REGISTRY_PORT,
        'name': DEFAULT_REGISTRY_NAME
    }
    
    if GLOBAL_CONFIG_FILE.is_file():
        config.read(GLOBAL_CONFIG_FILE)
        
    return config

def save_global_config(config: configparser.ConfigParser):
    """Saves the global config file."""
    try:
        GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(GLOBAL_CONFIG_FILE, 'w') as f:
            config.write(f)
    except Exception as e:
        print(f"Warning: Could not save global config file: {e}")

# --- Public Getter Functions ---

def get_registry_address() -> str:
    """Gets the full registry address (e.g., 'localhost:5000')."""
    config = _load_config()
    host = config.get('registry', 'host', fallback=DEFAULT_REGISTRY_HOST)
    port = config.get('registry', 'port', fallback=DEFAULT_REGISTRY_PORT)
    return f"{host}:{port}"

def get_registry_name() -> str:
    """Gets the name of the registry container (e.g., 'debox-registry')."""
    config = _load_config()
    return config.get('registry', 'name', fallback=DEFAULT_REGISTRY_NAME)