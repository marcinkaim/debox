# debox/commands/reinstall_cmd.py

from pathlib import Path
from typing import Optional
from debox.core import config_utils, hash_utils
from debox.core.log_utils import log_debug, log_info, log_error, console
from debox.commands import install_cmd
from debox.commands import remove_cmd

def reinstall_app(container_name: str, config_path: Optional[Path]):
    """
    Forces a clean reinstall by running 'remove' (without purge)
    and then 'install' (which finds the existing config or uses the new one).
    """
    log_info(f"--- Reinstalling application: {container_name} ---")
    
    app_config_dir = config_utils.get_app_config_dir(container_name, create=False)
    installation_status = hash_utils.get_installation_status(app_config_dir)
    
    if not config_path and not (app_config_dir / "config.yml").is_file():
        log_error(f"Cannot reinstall '{container_name}': Configuration file not found.", exit_program=True)
        print("   If this is a new installation, use 'debox install --config ...'")
        return

    try:
        if installation_status == hash_utils.STATUS_INSTALLED:
            log_info(f"-> Step 1: Removing existing installation artifacts...")
            remove_cmd.remove_app(container_name, purge_home=False)
        else:
            log_info(f"-> Step 1: Application not currently installed, skipping removal.")
        
        log_info(f"\n-> Step 2: Installing application from configuration...")
        install_cmd.install_app(container_name, config_path) 

        log_info(f"\n✅ Reinstall of '{container_name}' complete.")

    except SystemExit:
        log_debug("-> Sub-command exited.")
        raise
    except Exception as e:
        log_error(f"Reinstall failed: {e}", exit_program=True)