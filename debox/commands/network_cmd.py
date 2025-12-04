# debox/commands/network_cmd.py

"""
Handles runtime network configuration changes.
"""

import sys
from debox.core import config_utils
from debox.commands import configure_cmd
from debox.commands import apply_cmd
from debox.core.log_utils import LogLevels, log_debug, log_error, log_info, log_warning, temp_log_level

def _set_network_permission(container_name: str, allow: bool):
    """
    Helper function to update the network permission and apply changes immediately.
    """
    allow_str = str(allow).lower() # Converts True to 'true', False to 'false'
    action_str = "Enabling" if allow else "Disabling"

    log_info(f"--- {action_str} network for {container_name} ---")

    # 1. Check if the change is even needed
    try:
        app_config_dir = config_utils.get_app_config_dir(container_name, create=False)
        config_path = app_config_dir / "config.yml"
        if not config_path.is_file():
            log_error(f"Configuration file not found for '{container_name}'.", exit_program=True)
            
        config = config_utils.load_config(config_path)
        current_setting = config.get('permissions', {}).get('network', True)
        
        if current_setting is allow:
            log_info(f"-> Network permission for '{container_name}' is already set to '{allow_str}'. No changes needed.")
            return

    except Exception as e:
        log_warning(f"Could not read current config, proceeding with update anyway. Error: {e}")
        # Continue even if we can't read, 'configure' will find the file

    # 2. Call the 'configure' command logic
    log_debug(f"--- Step 1: Setting 'permissions.network' to '{allow_str}' ---")
    with temp_log_level(LogLevels.WARNING):
        try:
            configure_cmd.configure_app(
                container_name=container_name,
                key="permissions.network",
                value=allow_str,
                action="set"
            )
        except SystemExit as e:
            if e.code != 0: log_error(f"Configuration step failed.", exit_program=True)
        except Exception as e:
            log_error(f"Configuration step failed: {e}", exit_program=True)

    # 3. Call the 'apply' command logic
    log_info("-> Applying changes (recreating container)...")
    log_debug(f"\n--- Step 2: Applying changes to '{container_name}' (this will recreate the container) ---")
    with temp_log_level(LogLevels.WARNING):
        try:
            apply_cmd.apply_changes(container_name)
        except SystemExit as e:
            if e.code != 0: log_error(f"Apply step failed.", exit_program=True)
        except Exception as e:
            log_error(f"Apply step failed: {e}", exit_program=True)

    log_info(f"\n✅ Network permission for '{container_name}' is now set to '{allow_str}' and applied.")


def allow_network(container_name: str):
    """
    Enables network access for the specified container (requires recreation).
    """
    _set_network_permission(container_name, allow=True)


def deny_network(container_name: str):
    """
    Disables network access for the specified container (requires recreation).
    """
    _set_network_permission(container_name, allow=False)