# debox/debox/commands/remove_cmd.py

import shutil

from debox.commands import image_cmd
from debox.core import container_ops, hash_utils
from debox.core import desktop_integration
from debox.core import config_utils
from debox.core.log_utils import log_debug, log_error, log_info, log_warning, run_step, console

def remove_app(container_name: str, purge_home: bool):
    """
    Removes application artifacts based on installation status and --purge flag.
    """
    console.print(f"--- Removing application: {container_name} ---", style="bold")

    app_config_dir = config_utils.get_app_config_dir(container_name, create=False)
    
    if not app_config_dir.is_dir():
        log_info(f"-> Application '{container_name}' is not installed (configuration directory not found). Nothing to remove.")
        log_info(f"\n✅ Removal of '{container_name}' complete (was not installed).")
        return

    installation_status = hash_utils.get_installation_status(app_config_dir)

    if installation_status == hash_utils.STATUS_NOT_INSTALLED and not purge_home:
        log_info(f"-> Application '{container_name}' is already uninstalled (but configured).")
        log_info("   (Run with --purge to remove remaining configuration and data.)")
        log_info(f"\n✅ Removal of '{container_name}' complete (was already uninstalled).")
        return
    
    config = {} 
    try:
        config_path = app_config_dir / "config.yml"
        if config_path.is_file():
            config = config_utils.load_config(config_path) 
            log_debug(f"-> Found configuration for '{container_name}'")
        else:
            log_warning(f"Configuration file not found. Cleanup may be partial.")
    except Exception as e:
        log_warning(f"Could not load configuration file. Cleanup may be partial. Error: {e}")

    with run_step(
        spinner_message="Removing desktop integration...",
        success_message="-> Desktop integration removed.",
        error_message="Error removing desktop integration"
    ):
        desktop_integration.remove_desktop_integration(container_name, config)

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

    if purge_home:
        image_name = container_name
        tag = "latest" 
        
        try:
            image_cmd.remove_image_from_registry(image_name, tag)
        except Exception as e:
            log_warning(f"Failed to remove image from registry (ignore if already removed): {e}")
            
        log_debug("--- Purging configuration and data ---")
        with run_step(
            spinner_message="Removing debox configuration...",
            success_message="-> Debox configuration directory removed.",
            error_message="Error removing debox configuration"
        ):
            if app_config_dir.is_dir():
                shutil.rmtree(app_config_dir)
            else:
                log_debug(f"-> Config directory not found, skipping: {app_config_dir}")
        
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
        try:
            log_debug("-> Updating installation status to NOT_INSTALLED.")
            hash_utils.set_installation_status(app_config_dir, hash_utils.STATUS_NOT_INSTALLED)
            hash_utils.clear_config_hashes_keep_digest(app_config_dir)
            log_info("-> Configuration and isolated home directory kept (use --purge to remove everything).")
        except Exception as e:
            log_error(f"Failed to update installation status: {e}")
        
    log_info(f"\n✅ Removal of '{container_name}' complete!")