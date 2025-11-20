# debox/commands/configure_cmd.py

from debox.core import hash_utils
from debox.core import config_utils
from debox.core.log_utils import log_debug, log_error, log_info

def configure_app(container_name: str, key: str, value: str, action: str):
    """
    Loads, modifies, and saves an application's configuration file
    and sets the .needs_apply flag.
    """
    log_debug(f"--- Configuring application: {container_name} ---")
    
    try:
        # 1. Find and load the config
        app_config_dir = config_utils.get_app_config_dir(container_name, create=False)
        if not app_config_dir.is_dir():
            log_error(f"Configuration directory for '{container_name}' not found.", exit_program=True)
            
        config_path = app_config_dir / "config.yml"
        if not config_path.is_file():
            log_error(f"config.yml not found for '{container_name}'.", exit_program=True)
            
        config = config_utils.load_config(config_path)

        # 2. Loop through and apply updates in memory
        log_debug(f"-> Applying change: {key}:{action}:{value}")
        try:
            config_utils.update_config_value(config, key, action, value)
            
        except (KeyError, TypeError, ValueError) as e:
            log_error(f"-> Applying update '{key}:{action}:{value}' failed: {e}", exit_program=True)

        # 3. Save the modified config file
        config_utils.save_config(config, config_path)
        
        # 4. Create the .needs_apply "dirty" flag
        hash_utils.create_needs_apply_flag(app_config_dir)

        log_info(f"\n✅ Successfully modified configuration for '{container_name}'.")
        log_info(f"   Run 'debox apply {container_name}' to apply changes.")

    except Exception as e:
        log_error(f"Configuring application {container_name} failed: {e}", exit_program=True)