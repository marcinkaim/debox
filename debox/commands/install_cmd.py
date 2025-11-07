# debox/commands/install_cmd.py

import shutil
from pathlib import Path
import os
from typing import Optional

from debox.core import config as config_utils
from debox.core import desktop_integration
from debox.core import container_ops
from debox.core import hash_utils
from debox.core.log_utils import log_debug, run_step, console, log_info, log_error, log_warning

def install_app(container_name: Optional[str], config_path: Optional[Path]):
    """
    Orchestrates the installation based on provided arguments.
    Validates if the app is already installed.
    """
    log_debug(f"--- Starting install command ---")
    log_debug(f"Provided container_name: {container_name}")
    log_debug(f"Provided config_path: {config_path}")

    config_from_file = None
    final_container_name = container_name
    
    if config_path:
        try:
            config_from_file = config_utils.load_config(config_path)
            name_from_file = config_from_file['container_name']
            
            if final_container_name is None:
                final_container_name = name_from_file
                log_debug(f"-> Container name from file: {final_container_name}")
            elif final_container_name != name_from_file:
                log_error(f"Name mismatch: Argument '{container_name}' does not match 'container_name: {name_from_file}' in file.", exit_program=True)
        except Exception as e:
            log_error(f"Error loading provided config file {config_path}: {e}", exit_program=True)
    
    if final_container_name is None:
        log_error("No container name provided and no --config file specified.", exit_program=True)

    app_config_dir = config_utils.get_app_config_dir(final_container_name)
    existing_config_path = app_config_dir / "config.yml"
    installation_status = hash_utils.get_installation_status(app_config_dir)
    is_installed = (installation_status == hash_utils.STATUS_INSTALLED)
    existing_config_exists = existing_config_path.is_file()

    final_config_to_install = None
    
    if config_from_file:
        if is_installed:
            log_debug("-> App is installed. Comparing provided config with existing.")
            config_from_existing = config_utils.load_config(existing_config_path)
            current_hashes = hash_utils.calculate_hashes(config_from_file)
            saved_hashes = hash_utils.calculate_hashes(config_from_existing)
            
            if current_hashes == saved_hashes:
                log_info(f"Application '{final_container_name}' is already installed with an identical configuration.")
                return
            else:
                log_error(f"Application '{final_container_name}' is installed, but the provided config is different." + 
                          "\n   To apply changes, use: 'debox configure ...' and 'debox apply ...'" +
                          "\n   To force reinstall with this file, run: 'debox remove {final_container_name}' and then 'debox install ...'", exit_program=True)
        else:
            if existing_config_exists:
                log_info(f"-> Overwriting existing (but not installed) configuration for '{final_container_name}'.")
            else:
                log_info(f"-> New installation for '{final_container_name}'.")
            
            try:
                shutil.copy(config_path, existing_config_path)
                log_debug(f"-> Copied new config to {existing_config_path}")
            except Exception as e:
                log_error(f"Failed to copy config file: {e}", exit_program=True)
            
            final_config_to_install = config_from_file
            
    else:
        if is_installed:
            log_info(f"Application '{final_container_name}' is already installed.")
            return
            
        if not existing_config_exists:
            log_error(f"Cannot install '{final_container_name}': Config file not found." +
                      "\n   To install a new app, you must provide the --config flag.", exit_program=True)
        
        log_info(f"-> Found existing config for '{final_container_name}'. Proceeding with re-installation.")
        final_config_to_install = config_utils.load_config(existing_config_path)

    config = final_config_to_install
    app_name = config.get('app_name', final_container_name)
    log_info(f"--- Installing application: {app_name} ({final_container_name}) ---")

    try:
        current_dir = Path(__file__).parent
        keep_alive_script_src = current_dir.parent / "core" / "keep_alive.py"
        if keep_alive_script_src.is_file():
            shutil.copy(keep_alive_script_src, app_config_dir / "keep_alive.py")
            log_debug(f"-> Copied keep_alive.py to build context.")
        
        local_debs = config.get('image', {}).get('local_debs', [])
        if local_debs:
            log_debug(f"-> Copying {len(local_debs)} local .deb package(s) to build context...")
            for deb_path_str in local_debs:
                deb_path = Path(os.path.expanduser(deb_path_str))
                if not deb_path.is_file():
                    raise FileNotFoundError(f"Local package not found: {deb_path}")
                dest_path = app_config_dir / deb_path.name
                shutil.copy(deb_path, dest_path)
                log_debug(f"--> Copied {deb_path.name}")
            
        console.print("-> Configuration loaded and prepared.")
    except Exception as e:
        log_error(f"Error preparing config directory: {e}", exit_program=True)
    
    with run_step(f"Building image 'localhost/{final_container_name}:latest'...", "-> Image built successfully.", "Error building image"):
        image_tag = container_ops.build_container_image(config, app_config_dir)
    
    with run_step(f"Creating container '{final_container_name}'...", "-> Container created successfully.", "Error creating container"):
        container_ops.create_container_instance(config, image_tag)
    
    with run_step("Applying desktop integration...", "-> Desktop integration applied.", "Error during desktop integration"):
        desktop_integration.add_desktop_integration(config)

    try:
        log_debug("-> Finalizing installation state...")
        current_hashes = hash_utils.calculate_hashes(config)
        hash_utils.save_last_applied_hashes(app_config_dir, current_hashes)
        hash_utils.set_installation_status(app_config_dir, hash_utils.STATUS_INSTALLED)
        hash_utils.remove_needs_apply_flag(app_config_dir)
        log_debug("-> Installation state finalized.")
    except Exception as e:
        log_warning(f"Could not finalize installation state: {e}")

    log_info(f"\n✅ Installation of '{app_name}' complete!")
