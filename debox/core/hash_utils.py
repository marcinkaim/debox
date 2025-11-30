# debox/core/hash_utils.py

"""
Handles calculating, saving, and comparing configuration hashes
to detect changes and determine required actions.
"""

import json
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional

from debox.core.log_utils import log_debug, log_error, log_warning

# Define the sections we care about hashing
SECTIONS_TO_HASH = ['image', 'storage', 'runtime', 'integration', 'permissions']

# --- Constants for state files ---
STATE_FILE_NAME = ".last_applied_state.json"
FLAG_FILE_NAME = ".needs_apply"
STATUS_FILE_NAME = ".installation_status"

# --- Constants for status ---
STATUS_INSTALLED = "INSTALLED"
STATUS_NOT_INSTALLED = "NOT_INSTALLED"

STATE_KEY_REGISTRY_DIGEST = "registry_digest"


def _calculate_section_hash(section_data: Any) -> str:
    """
    Seralizes a config section and returns its SHA256 hash.
    """
    if section_data is None:
        return hashlib.sha256(b"").hexdigest()
        
    # Serialize the section to JSON in a consistent (sorted) way
    # This ensures that {'a': 1, 'b': 2} and {'b': 2, 'a': 1} produce the same hash.
    serialized_data = json.dumps(section_data, sort_keys=True).encode('utf-8')
    
    return hashlib.sha256(serialized_data).hexdigest()

def calculate_hashes(config: dict) -> Dict[str, str]:
    """
    Calculates hashes for key configuration sections to detect changes.
    Splits integration into 'full' and 'critical' to optimize apply logic.
    """
    hashes = {}
    
    # Standardowe sekcje
    for section in ['image', 'storage', 'runtime', 'permissions']:
        hashes[section] = _calculate_section_hash(config.get(section, {}))
    
    # Specjalna obsługa sekcji 'integration'
    int_conf = config.get('integration', {})
    
    # 1. Pełny hash (do wykrywania jakichkolwiek zmian, np. aliasów)
    hashes['integration'] = _calculate_section_hash(int_conf)
    
    # 2. Hash krytyczny (tylko opcje wpływające na flagi 'podman create')
    # Obecnie tylko 'desktop_integration' (bool) wpływa na montowanie gniazd/X11
    critical_data = {'desktop_integration': int_conf.get('desktop_integration', True)}
    hashes['integration_critical'] = _calculate_section_hash(critical_data)

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
        log_warning(f"Could not read state file {state_file}: {e}")
        return {} # Treat unreadable state as needing update

def save_last_applied_hashes(app_config_dir: Path, hashes: Dict[str, str]):
    """
    Saves the given hashes to the .last_applied_state.json file.
    """
    state_file = app_config_dir / STATE_FILE_NAME
    try:
        with open(state_file, 'w') as f:
            json.dump(hashes, f, indent=2)
        log_debug(f"-> Saved applied state to {state_file}")
    except Exception as e:
        log_error(f"Saving applied state to {state_file} failed: {e}")

def remove_last_applied_hashes(app_config_dir: Path):
    """
    Removes the .last_applied_state.json file.
    """
    state_file = app_config_dir / STATE_FILE_NAME
    if state_file.is_file():
        try:
            state_file.unlink()
        except Exception as e:
            log_warning(f"Could not remove state file {state_file}: {e}")

def create_needs_apply_flag(app_config_dir: Path):
    """
    Creates the .needs_apply flag file to signal a configuration change.
    """
    try:
        (app_config_dir / FLAG_FILE_NAME).touch()
        log_debug(f"-> Flagged '{app_config_dir.name}' as needing apply.")
    except Exception as e:
        log_warning(f"Could not create .needs_apply flag: {e}")
        
def remove_needs_apply_flag(app_config_dir: Path):
    """
    Removes the .needs_apply flag file after changes are applied.
    """
    flag_file = app_config_dir / FLAG_FILE_NAME
    if flag_file.is_file():
        try:
            flag_file.unlink()
        except Exception as e:
            log_warning(f"Could not remove .needs_apply flag: {e}")

def get_installation_status(app_config_dir: Path) -> str:
    """
    Checks the installation status file for an app.
    Defaults to NOT_INSTALLED if the file or directory doesn't exist.
    """
    status_file = app_config_dir / STATUS_FILE_NAME
    if not status_file.is_file():
        # If the config dir doesn't even exist, it's definitely not installed
        log_debug(f"Status file not found at {status_file}. Defaulting to NOT_INSTALLED.")
        return STATUS_NOT_INSTALLED
    
    try:
        status = status_file.read_text().strip()
        if status in (STATUS_INSTALLED, STATUS_NOT_INSTALLED):
            return status
        else:
            log_warning(f"Unknown status '{status}' in {status_file}. Defaulting to NOT_INSTALLED.")
            return STATUS_NOT_INSTALLED
    except Exception as e:
        log_warning(f"Could not read status file {status_file}: {e}. Defaulting to NOT_INSTALLED.")
        return STATUS_NOT_INSTALLED

def set_installation_status(app_config_dir: Path, status: str):
    """
    Writes the installation status (INSTALLED or NOT_INSTALLED) to the file.
    """
    if status not in (STATUS_INSTALLED, STATUS_NOT_INSTALLED):
        raise ValueError(f"Invalid status '{status}'. Must be INSTALLED or NOT_INSTALLED.")
        
    status_file = app_config_dir / STATUS_FILE_NAME
    try:
        # Ensure the parent directory exists
        app_config_dir.mkdir(parents=True, exist_ok=True)
        status_file.write_text(status)
        log_debug(f"-> Set installation status to '{status}' in {status_file}")
    except Exception as e:
        log_error(f"Failed to write installation status to {status_file}: {e}", exit_program=True)

def remove_installation_status_file(app_config_dir: Path):
    """
    Removes the .installation_status file. Used during --purge.
    """
    status_file = app_config_dir / STATUS_FILE_NAME
    if status_file.is_file():
        try:
            status_file.unlink()
        except Exception as e:
            log_warning(f"Could not remove status file {status_file}: {e}")

def save_image_digest(app_config_dir: Path, digest: str):
    """
    Saves digest of pushed image to state file.
    """
    state_file = app_config_dir / STATE_FILE_NAME
    # Wczytaj istniejące hashe, aby ich nie nadpisać
    hashes = get_last_applied_hashes(app_config_dir)
    
    # Dodaj lub zaktualizuj digest
    hashes[STATE_KEY_REGISTRY_DIGEST] = digest
    
    # Zapisz z powrotem
    save_last_applied_hashes(app_config_dir, hashes)
    log_debug(f"-> Saved registry digest {digest} to {state_file}")

def get_image_digest(app_config_dir: Path) -> Optional[str]:
    """
    Reads saved digest from state file.
    """
    hashes = get_last_applied_hashes(app_config_dir)
    return hashes.get(STATE_KEY_REGISTRY_DIGEST)

def remove_image_digest(app_config_dir: Path):
    """
    Removes digest from state file.
    """
    hashes = get_last_applied_hashes(app_config_dir)
    if STATE_KEY_REGISTRY_DIGEST in hashes:
        del hashes[STATE_KEY_REGISTRY_DIGEST]
        save_last_applied_hashes(app_config_dir, hashes)

def clear_config_hashes_keep_digest(app_config_dir: Path):
    """
    Removes configuration hashes from the state file but keeps the registry digest.
    Used when uninstalling an app without purging (so we can still remove the image later).
    """
    hashes = get_last_applied_hashes(app_config_dir)
    digest = hashes.get(STATE_KEY_REGISTRY_DIGEST)
    
    new_state = {}
    if digest:
        new_state[STATE_KEY_REGISTRY_DIGEST] = digest
        
    save_last_applied_hashes(app_config_dir, new_state)