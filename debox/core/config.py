# debox/core/config.py

from pathlib import Path
import yaml
import os

from debox.core.log_utils import log_debug, log_error

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
    log_debug(f"-> Loading configuration from {config_path}...")
    if not config_path.is_file():
        raise ValueError(f"Configuration file not found: {config_path}")

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # Basic validation to ensure required keys are present.
    required_keys = ['app_name', 'container_name', 'image']
    for key in required_keys:
        if key not in config:
            raise ValueError(f"Missing required key in config file: '{key}'")
    
    log_debug("-> Configuration loaded and validated successfully.")
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

def save_config(config: dict, config_path: Path):
    """
    Saves a configuration dictionary back to a YAML file.
    """
    try:
        with open(config_path, 'w') as f:
            yaml.dump(config, f, sort_keys=False, default_flow_style=False)
        log_debug(f"-> Configuration saved to {config_path}")
    except Exception as e:
        log_error(f"Saving configuration to {config_path} failed: {e}")
        raise

def _convert_type(value_str: str):
    """
    Naively converts "true"/"false" strings to booleans.
    """
    val_lower = value_str.lower()
    if val_lower == 'true':
        return True
    if val_lower == 'false':
        return False
    # Could add int/float conversion, but string is safest for now
    return value_str

def update_config_value(config: dict, path_str: str, action: str, value_str: str):
    """
    Navigates a config dict using a dot-notation path and applies an action.
    This function modifies the 'config' dictionary in-place.
    It creates nested dictionaries if they don't exist for 'set' actions.
    """
    keys = path_str.split('.')
    parent = config
    
    # Traverse/create path up to the *parent* of the final key
    for key in keys[:-1]:
        # If we are setting a value, create dictionaries if they don't exist
        if action in ('set', 'add', 'set_map'):
            # setdefault is perfect: it gets the key, or creates it if not found
            parent = parent.setdefault(key, {}) 
            if not isinstance(parent, dict):
                 # This handles config errors, e.g., trying 'integration.aliases.foo:bar'
                 # when 'integration.aliases' is a list, not a dict.
                 raise TypeError(f"Path conflict: '{key}' in '{path_str}' exists but is not a dictionary.")
        else:
            # If we are removing/unsetting, the path MUST exist
            parent = parent.get(key)
            if not isinstance(parent, dict):
                 raise KeyError(f"Invalid path: Section '{key}' not found or not a dictionary in '{path_str}'.")

    final_key = keys[-1]

    # --- Handle actions on the final_key ---

    if action == 'set':
        # Simple value replacement, creates key if not exists
        typed_value = _convert_type(value_str)
        parent[final_key] = typed_value
        log_debug(f"  - Set: {path_str} = {typed_value}")
    
    elif action == 'add':
        # Add to a list, creates list if not exists
        target_list = parent.setdefault(final_key, []) # Get list or create new empty list
        if isinstance(target_list, list):
            typed_value = _convert_type(value_str)
            target_list.append(typed_value)
            log_debug(f"  - Added: {value_str} to {path_str}")
        else:
            raise TypeError(f"Cannot 'add' to non-list key: {path_str}")
            
    elif action == 'remove':
        # Remove from an *existing* list
        target_list = parent.get(final_key) # Must exist
        if target_list is None:
            raise KeyError(f"Invalid path: List '{final_key}' not found in section '{'.'.join(keys[:-1])}'.")
        if isinstance(target_list, list):
            typed_value = _convert_type(value_str)
            try:
                target_list.remove(typed_value)
            except ValueError:
                try:
                    target_list.remove(value_str) # Fallback to raw string
                except ValueError:
                     raise ValueError(f"Value '{value_str}' not found in list {path_str}")
            log_debug(f"  - Removed: {value_str} from {path_str}")
        else:
            raise TypeError(f"Cannot 'remove' from non-list key: {path_str}")
            
    elif action == 'set_map':
        # Set a key-value pair in a dictionary, creates dict if not exists
        target_map = parent.setdefault(final_key, {}) # Get map or create new empty map
        if not isinstance(target_map, dict):
             raise TypeError(f"Cannot 'set_map' on non-dict key: {path_str}")
        try:
            k, v = value_str.split('=', 1)
        except ValueError:
            raise ValueError("Invalid map format. Expected 'key=value'.")
        target_map[k.strip()] = v.strip() # Store value as string
        log_debug(f"  - Set Map: {path_str}.{k.strip()} = {v.strip()}")
            
    elif action == 'unset_map':
        # Remove a key from an *existing* dictionary
         target_map = parent.get(final_key) # Must exist
         if target_map is None:
            raise KeyError(f"Invalid path: Map '{final_key}' not found in section '{'.'.join(keys[:-1])}'.")
         if isinstance(target_map, dict):
            try:
                del target_map[value_str]
                log_debug(f"  - Unset Map: Removed key {value_str} from {path_str}")
            except KeyError:
                raise KeyError(f"Key '{value_str}' not found in map {path_str}")
         else:
            raise TypeError(f"Cannot 'unset_map' on non-dict key: {path_str}")
    
    else:
         raise ValueError(f"Unknown action: '{action}'")

    return config # Return modified config