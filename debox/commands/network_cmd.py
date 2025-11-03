# debox/commands/network_cmd.py

"""
Handles runtime network changes by acting as a shortcut for
'debox configure' and 'debox apply'.
"""

import sys
from debox.core import config as config_utils
# Import the command logic we are going to call
from debox.commands import configure_cmd
from debox.commands import apply_cmd
from debox.core.log_utils import log_verbose, console

def _set_network_permission(container_name: str, allow: bool):
    """
    Internal helper function to configure and apply the network setting.
    
    Args:
        container_name: The name of the container to modify.
        allow: True to allow network, False to deny.
    """
    allow_str = str(allow).lower() # Converts True to 'true', False to 'false'
    action_str = "Enabling" if allow else "Disabling"

    console.print(f"--- {action_str} network for {container_name} ---")

    # 1. Check if the change is even needed
    try:
        app_config_dir = config_utils.get_app_config_dir(container_name, create=False)
        config_path = app_config_dir / "config.yml"
        if not config_path.is_file():
            console.print(f"❌ Error: Configuration file not found for '{container_name}'.", style="bold red")
            sys.exit(1)
            
        config = config_utils.load_config(config_path)
        current_setting = config.get('permissions', {}).get('network', True)
        
        if current_setting is allow:
            console.print(f"-> Network permission for '{container_name}' is already set to '{allow_str}'. No changes needed.", style="bold red")
            return

    except Exception as e:
        console.print(f"Warning: Could not read current config, proceeding with update anyway. Error: {e}", style="bold red")
        # Continue even if we can't read, 'configure' will find the file

    # 2. Call the 'configure' command logic
    log_verbose(f"--- Step 1: Setting 'permissions.network' to '{allow_str}' ---")
    try:
        config_string = f"permissions.network:{allow_str}"
        configure_cmd.configure_app(container_name, [config_string], silent=True)
    except SystemExit as e:
        if e.code != 0: # Check if configure_app exited with an error
            console.print(f"❌ Error during configuration step. Halting.", style="bold red")
            return # Don't proceed to apply
    except Exception as e:
        console.print(f"❌ Error during configuration step: {e}. Halting.", style="bold red")
        return

    # 3. Call the 'apply' command logic
    console.print("-> Applying changes (recreating container)...")
    log_verbose(f"\n--- Step 2: Applying changes to '{container_name}' (this will recreate the container) ---")
    try:
        apply_cmd.apply_changes(container_name, silent=True)
    except SystemExit as e:
         if e.code != 0:
            console.print(f"❌ Error during apply step. Configuration is modified but not applied.", style="bold red")
            return
    except Exception as e:
        console.print(f"❌ Error during apply step: {e}. Configuration is modified but not applied.", style="bold red")
        return

    console.print(f"\n✅ Network permission for '{container_name}' has been set to '{allow_str}' and applied.")


def allow_network(container_name: str):
    """
    Public function to set network permission to 'true' and apply the change.
    """
    _set_network_permission(container_name, allow=True)


def deny_network(container_name: str):
    """
    Public function to set network permission to 'false' and apply the change.
    """
    _set_network_permission(container_name, allow=False)