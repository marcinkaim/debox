# debox/core/hash_utils.py

"""
Handles calculating, saving, and comparing configuration hashes
to detect changes and determine required actions.
"""

import json
import hashlib
from pathlib import Path
from typing import Dict, Any

# Define the sections we care about hashing
SECTIONS_TO_HASH = ['image', 'storage', 'runtime', 'integration', 'permissions']
STATE_FILE_NAME = ".last_applied_state.json"
FLAG_FILE_NAME = ".needs_apply"


def _calculate_section_hash(section_data: Any) -> str:
    """
Seralizes a config section and returns its SHA256 hash."""
    if section_data is None:
        return hashlib.sha256(b"").hexdigest()
        
    # Serialize the section to JSON in a consistent (sorted) way
    # This ensures that {'a': 1, 'b': 2} and {'b': 2, 'a': 1} produce the same hash.
    serialized_data = json.dumps(section_data, sort_keys=True).encode('utf-8')
    
    return hashlib.sha256(serialized_data).hexdigest()

def calculate_hashes(config: dict) -> Dict[str, str]:
    """
    Calculates the SHA256 hash for each managed section in the config.
    """
    hashes = {}
    for section in SECTIONS_TO_HASH:
        section_data = config.get(section)
        hashes[section] = _calculate_section_hash(section_data)
    return hashes

def get_last_applied_hashes(app_config_dir: Path) -> Dict[str, str]:
    """
    Loads the saved hashes from the .last_applied_state.json file.
    Returns an empty dict if the file is not found.
    """
    state_file = app_config_dir / STATE_FILE_NAME
    if not state_file.is_file():
        return {} # No state file means it's a new install

    try:
        with open(state_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Could not read state file {state_file}: {e}")
        return {} # Treat unreadable state as needing update

def save_last_applied_hashes(app_config_dir: Path, hashes: Dict[str, str]):
    """
    Saves the given hashes to the .last_applied_state.json file.
    """
    state_file = app_config_dir / STATE_FILE_NAME
    try:
        with open(state_file, 'w') as f:
            json.dump(hashes, f, indent=2)
        print(f"-> Saved applied state to {state_file}")
    except Exception as e:
        print(f"❌ Error saving applied state to {state_file}: {e}")

def remove_last_applied_hashes(app_config_dir: Path):
    """
    Removes the .last_applied_state.json file.
    """
    state_file = app_config_dir / STATE_FILE_NAME
    if state_file.is_file():
        try:
            state_file.unlink()
        except Exception as e:
            print(f"Warning: Could not remove state file {state_file}: {e}")

def create_needs_apply_flag(app_config_dir: Path):
    """
    Creates the .needs_apply flag file to signal a configuration change.
    """
    try:
        (app_config_dir / FLAG_FILE_NAME).touch()
        print(f"-> Flagged '{app_config_dir.name}' as needing apply.")
    except Exception as e:
        print(f"Warning: Could not create .needs_apply flag: {e}")
        
def remove_needs_apply_flag(app_config_dir: Path):
    """
    Removes the .needs_apply flag file after changes are applied.
    """
    flag_file = app_config_dir / FLAG_FILE_NAME
    if flag_file.is_file():
        try:
            flag_file.unlink()
        except Exception as e:
            print(f"Warning: Could not remove .needs_apply flag: {e}")