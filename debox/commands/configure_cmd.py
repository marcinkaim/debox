# debox/commands/configure_cmd.py

import sys
from pathlib import Path
from debox.core import config as config_utils, hash_utils
from debox.core.log_utils import log_verbose

def configure_app(container_name: str, updates: list[str], silent: bool = False):
    """
    Loads, modifies, and saves an application's configuration file
    and sets the .needs_apply flag.
    """
    log_verbose(f"--- Configuring application: {container_name} ---")
    
    try:
        # 1. Find and load the config
        app_config_dir = config_utils.get_app_config_dir(container_name, create=False)
        if not app_config_dir.is_dir():
            print(f"❌ Error: Configuration directory for '{container_name}' not found.")
            sys.exit(1)
            
        config_path = app_config_dir / "config.yml"
        if not config_path.is_file():
            print(f"❌ Error: config.yml not found for '{container_name}'.")
            sys.exit(1)
            
        config = config_utils.load_config(config_path)

        # 2. Loop through and apply updates in memory
        log_verbose("-> Applying requested changes:")
        modified = False
        for update_str in updates:
            try:
                # Parse the update string
                parts = update_str.split(':', 2)
                path_str: str = ""
                action: str = ""
                value_str: str = ""

                if len(parts) == 2:
                    # Format: "section.key:value"
                    path_str = parts[0]
                    action = "set"
                    value_str = parts[1]
                elif len(parts) == 3:
                    # Format: "section.key:action:value"
                    path_str = parts[0]
                    action = parts[1].lower()
                    value_str = parts[2]
                else:
                    raise ValueError(f"Invalid update format: '{update_str}'. Expected 'path:value' or 'path:action:value'.")

                # Apply the change to the config dictionary
                config_utils.update_config_value(config, path_str, action, value_str)
                modified = True
            except (KeyError, TypeError, ValueError) as e:
                print(f"-> ❌ Error applying update '{update_str}': {e}")
                print("-> Halting configuration. No changes will be saved.")
                sys.exit(1)

        # 3. Save the modified config file
        if modified:
            config_utils.save_config(config, config_path)
            
            # 4. Create the .needs_apply "dirty" flag
            hash_utils.create_needs_apply_flag(app_config_dir)

            if not silent:
                print(f"\n✅ Successfully modified configuration for '{container_name}'.")
                print(f"   Run 'debox apply {container_name}' to apply changes.")
        else:
            if not silent:
                print("-> No updates specified or no changes made.")

    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")
        sys.exit(1)