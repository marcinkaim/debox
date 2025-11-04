# debox/debox/commands/remove_cmd.py

import shutil

from debox.core import config as config_utils, container_ops
from debox.core import desktop_integration
from debox.core.log_utils import log_debug, log_info, log_warning, run_step

def remove_app(container_name: str, purge_home: bool):
    """
    Finds and removes all components of a debox application,
    identified by its unique container name.
    """
    log_info(f"--- Removing application associated with container: {container_name} ---")

    # Load config (needed for desktop integration cleanup)
    config = {} 
    try:
        app_config_dir = config_utils.get_app_config_dir(container_name, create=False)
        config_path = app_config_dir / "config.yml"
        if config_path.is_file():
            config = config_utils.load_config(config_path)
            log_debug(f"-> Found configuration for '{container_name}' at {config_path}")
        else:
            log_warning(f"Configuration file not found. Cleanup may be partial.")
    except Exception as e:
        log_warning(f"Could not load configuration file. Cleanup may be partial. Error: {e}")

    # --- 1. Remove Desktop Integration ---
    with run_step(
        spinner_message="Removing desktop integration...",
        success_message="-> Desktop integration removed.",
        error_message="Error removing desktop integration"
    ):
        desktop_integration.remove_desktop_integration(container_name, config)
        
    # --- 2. Remove Podman Resources using container_ops ---
    with run_step(
        spinner_message="Removing Podman container...",
        success_message="-> Container instance removed.",
        error_message="Error removing Podman container"
    ):
        container_ops.remove_container_instance(container_name)

    with run_step(
        spinner_message="Removing Podman image...",
        success_message="-> Container image removed.",
        error_message="Error removing Podman image"
    ):
        container_ops.remove_container_image(container_name)  

    # --- 3. Remove Debox Configuration ---
    with run_step(
        spinner_message="Removing debox configuration...",
        success_message="-> Debox configuration directory removed.",
        error_message="Error removing debox configuration"
    ):
        app_config_dir = config_utils.get_app_config_dir(container_name, create=False)
        if app_config_dir.is_dir():
            shutil.rmtree(app_config_dir)
        else:
            log_debug(f"-> Config directory not found, skipping: {app_config_dir}")
        
    # --- Optionally Remove Isolated Home ---
    if purge_home:
        with run_step(
            spinner_message="Purging isolated home directory...",
            success_message="-> Isolated home directory purged.",
            error_message="Error purging home directory"
        ):
            app_home_dir = config_utils.get_app_home_dir(container_name, create=False)
            if app_home_dir.is_dir():
                shutil.rmtree(app_home_dir)
            else:
                log_debug(f"-> Isolated home directory not found, skipping: {app_home_dir}")
    else:
        log_info("-> Isolated home directory kept (use --purge to remove).")
        
    log_info(f"\n✅ Removal associated with '{container_name}' complete.")