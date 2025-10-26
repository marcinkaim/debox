# debox/core/config.py

from pathlib import Path
import yaml
import os

# Define constants for configuration directories.
# Using os.path.expanduser('~') makes it work for any user.
DEBOX_APPS_DIR = Path(os.path.expanduser("~/.config/debox/apps"))
DEBOX_HOMES_DIR = Path(os.path.expanduser("~/.local/share/debox/homes"))
DESKTOP_FILES_DIR = Path(os.path.expanduser("~/.local/share/applications"))

def load_config(config_path: Path) -> dict:
    """
    Loads and validates an application's YAML configuration file.

    Args:
        config_path: The path to the .yml file.

    Returns:
        A dictionary containing the parsed configuration.

    Raises:
        ValueError: If the file is invalid or missing required keys.
    """
    print(f"-> Loading configuration from {config_path}...")
    if not config_path.is_file():
        raise ValueError(f"Configuration file not found: {config_path}")

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # Basic validation to ensure required keys are present.
    required_keys = ['app_name', 'container_name', 'image']
    for key in required_keys:
        if key not in config:
            raise ValueError(f"Missing required key in config file: '{key}'")
    
    print("-> Configuration loaded and validated successfully.")
    return config

def get_app_config_dir(container_name: str, create: bool = True) -> Path:
    """
    Returns the path to the application's specific config directory.
    e.g., ~/.config/debox/apps/debox-vscode/
    """
    app_dir = DEBOX_APPS_DIR / container_name
    if create:
        app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir

def get_app_home_dir(container_name: str, create: bool = True) -> Path:
    """
    Returns the path to the application's isolated home directory.
    e.g., ~/.local/share/debox/homes/debox-vscode/
    """
    home_dir = DEBOX_HOMES_DIR / container_name
    if create:
        home_dir.mkdir(parents=True, exist_ok=True)
    return home_dir