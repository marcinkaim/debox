# debox/commands/apply_cmd.py

import shutil
from pathlib import Path

from debox.core import config_utils, registry_utils
from debox.core import hash_utils
from debox.core import container_ops
from debox.core import desktop_integration
from debox.core.log_utils import log_debug, log_error, log_info, log_warning, run_step

def apply_changes(container_name: str):
    """
    Compares current config hashes against saved state and performs
    rebuild, recreate, or reintegration actions as needed.
    """
    log_debug(f"--- Applying configuration changes for: {container_name} ---")

    image_digest = None
    
    try:
        # 1. Load configurations
        app_config_dir = config_utils.get_app_config_dir(container_name, create=False)
        if not app_config_dir.is_dir():
            log_error(f"Configuration directory for '{container_name}' not found.", exit_program=True)
            
        config_path = app_config_dir / "config.yml"
        if not config_path.is_file():
            log_error(f"config.yml not found for '{container_name}'.", exit_program=True)

        # Load the CURRENT desired state from config.yml
        current_config = config_utils.load_config(config_path)

        # Load the LAST APPLIED state from .json file
        saved_hashes = hash_utils.get_last_applied_hashes(app_config_dir)
        
        # Calculate hashes for the CURRENT desired state
        current_hashes = hash_utils.calculate_hashes(current_config)

        # 2. Compare hashes and plan actions
        image_changed = (current_hashes['image'] != saved_hashes.get('image'))
        storage_changed = (current_hashes['storage'] != saved_hashes.get('storage'))
        runtime_changed = (current_hashes['runtime'] != saved_hashes.get('runtime'))
        permissions_changed = (current_hashes['permissions'] != saved_hashes.get('permissions'))
        integration_any_changed = (current_hashes['integration'] != saved_hashes.get('integration'))
        integration_critical_changed = (current_hashes['integration_critical'] != saved_hashes.get('integration_critical'))

        do_rebuild = image_changed
        do_recreate = do_rebuild or storage_changed or runtime_changed or permissions_changed or integration_critical_changed
        do_reintegrate = do_recreate or integration_any_changed

        if not do_rebuild and not do_recreate and not do_reintegrate: # This implicitly covers 'no changes'
            log_debug("-> Configuration is already up to date.")
            hash_utils.remove_needs_apply_flag(app_config_dir)
            log_info("\n✅ Apply complete. No changes needed.")
            return

        log_info("--- Change detected. Applying updates ---")
        
        # 3. Execute actions in correct order
        
        # 3a. Remove old desktop integration (must happen before container is destroyed)
        if do_reintegrate:
            with run_step(
                spinner_message="Removing old desktop integration...",
                success_message="-> Desktop integration removed.",
                error_message="Error removing old desktop integration"
            ):
                desktop_integration.remove_desktop_integration(container_name, current_config)

        # 3b. Remove old container
        if do_recreate:
            with run_step(
                spinner_message="Removing old container instance...",
                success_message="-> Container instance removed.",
                error_message="Error removing container instance"
            ):
                container_ops.remove_container_instance(container_name)

        # 3c. Rebuild image (if needed)
        image_tag = f"localhost/{container_name}:latest" # Default tag
        if do_rebuild:
            with run_step(
                spinner_message="Removing old container image...",
                success_message="-> Old container image removed.",
                error_message="Error removing old image"
            ):
                container_ops.remove_container_image(container_name)
            
            # Copy keep_alive script (this logic must be present, same as install)
            log_debug("-> Copying keep_alive.py to build context...")
            try:
                current_dir = Path(__file__).parent
                keep_alive_script_src = current_dir.parent / "core" / "keep_alive.py"
                if keep_alive_script_src.is_file():
                    shutil.copy(keep_alive_script_src, app_config_dir / "keep_alive.py")
            except Exception as e:
                 log_warning(f"Warning: Failed to copy keep_alive.py: {e}")
            
            # Build the new image
            with run_step(
                spinner_message=f"Building image 'localhost/{container_name}:latest'...",
                success_message="-> Container image rebuilt.",
                error_message="Building image failed"
            ):
                image_tag = container_ops.build_container_image(current_config, app_config_dir)

            with run_step(
                spinner_message="Backing up rebuilt image to local registry...",
                success_message="-> Rebuilt image backed up.",
                error_message="Error backing up image"
            ):
                image_digest = registry_utils.push_image_to_registry(image_tag)

        # 3d. Create new container
        if do_recreate:
            with run_step(
                spinner_message="Creating new container instance...",
                success_message="-> Container instance created.",
                error_message="Error creating container instance"
            ):
                container_ops.create_container_instance(current_config, image_tag)

        # 3e. Add new desktop integration
        if do_reintegrate:
            with run_step(
                spinner_message="Applying new desktop integration...",
                success_message="-> Desktop integration applied.",
                error_message="Error applying desktop integration"
            ):
                desktop_integration.add_desktop_integration(current_config)

        # 4. Finalize state
        log_debug("-> Finalizing new configuration state...")

        if image_digest:
            pass
        else:
            old_state = hash_utils.get_last_applied_hashes(app_config_dir)
            image_digest = old_state.get(hash_utils.STATE_KEY_REGISTRY_DIGEST)

        current_hashes[hash_utils.STATE_KEY_REGISTRY_DIGEST] = image_digest

        hash_utils.save_last_applied_hashes(app_config_dir, current_hashes)
        hash_utils.set_installation_status(app_config_dir, hash_utils.STATUS_INSTALLED)
        hash_utils.remove_needs_apply_flag(app_config_dir)

        log_info("\n✅ Apply complete. Changes have been applied.")

    except Exception as e:
        # Mark as still needing apply
        if 'app_config_dir' in locals():
            hash_utils.create_needs_apply_flag(app_config_dir)

        log_error(f"Applying configuration for application {container_name} failed: {e}", exit_program=True)