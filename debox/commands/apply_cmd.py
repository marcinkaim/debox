# debox/commands/apply_cmd.py

import sys
import shutil
from pathlib import Path

from debox.core import config as config_utils
from debox.core import hash_utils
from debox.core import container_ops
from debox.core import desktop_integration
from debox.core.log_utils import log_verbose

def apply_changes(container_name: str, silent: bool = False):
    """
    Compares current config hashes against saved state and performs
    rebuild, recreate, or reintegration actions as needed.
    """
    log_verbose(f"--- Applying configuration changes for: {container_name} ---")
    
    try:
        # 1. Load configurations
        app_config_dir = config_utils.get_app_config_dir(container_name, create=False)
        if not app_config_dir.is_dir():
            print(f"❌ Error: Configuration directory for '{container_name}' not found.")
            sys.exit(1)
            
        config_path = app_config_dir / "config.yml"
        if not config_path.is_file():
            print(f"❌ Error: config.yml not found for '{container_name}'.")
            sys.exit(1)

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
        integration_changed = (current_hashes['integration'] != saved_hashes.get('integration'))

        # Determine required actions based on MVP logic
        # (Any change in runtime/storage/perms/integration requires recreate for simplicity)
        do_rebuild = image_changed
        do_recreate = do_rebuild or storage_changed or runtime_changed or permissions_changed or integration_changed
        
        # We must re-integrate if we recreate, OR if only integration settings changed
        # Note: do_recreate already includes integration_changed, so this is simplified
        do_reintegrate = do_recreate 

        if not do_rebuild and not do_recreate and not do_reintegrate: # This implicitly covers 'no changes'
            log_verbose("-> Configuration is already up to date.")
            hash_utils.remove_needs_apply_flag(app_config_dir)
            if not silent:
                print("\n✅ Apply complete. No changes needed.")
            return

        if not silent:
            print("--- Change detected. Applying updates ---")
        
        # 3. Execute actions in correct order
        
        # 3a. Remove old desktop integration (must happen before container is destroyed)
        if do_reintegrate:
            log_verbose("-> Removing old desktop integration...")
            # Pass the SAVED config (or empty dict) in case old alias names are needed
            # Note: Our remove logic is smart and uses file prefixes, so this is robust
            desktop_integration.remove_desktop_integration(container_name, {}) 
            if not silent:
                print("-> Desktop integration removed.")

        # 3b. Remove old container
        if do_recreate:
            log_verbose("-> Removing old container instance...")
            container_ops.remove_container_instance(container_name)
            if not silent:
                print("-> Container instance removed.")

        # 3c. Rebuild image (if needed)
        image_tag = f"localhost/{container_name}:latest" # Default tag
        if do_rebuild:
            if not silent:
                print("-> Rebuilding container image... (This may take a while)")
            # Remove old image
            container_ops.remove_container_image(container_name)
            
            # Copy keep_alive script (this logic must be present, same as install)
            current_dir = Path(__file__).parent
            keep_alive_script_src = current_dir.parent / "core" / "keep_alive.py"
            if keep_alive_script_src.is_file():
                shutil.copy(keep_alive_script_src, app_config_dir / "keep_alive.py")
            
            # Build the new image
            image_tag = container_ops.build_container_image(current_config, app_config_dir)
            if not silent:
                print("-> Container image rebuilt.")

        # 3d. Create new container
        if do_recreate:
            log_verbose("-> Creating new container instance...")
            container_ops.create_container_instance(current_config, image_tag)
            if not silent:
                print("-> Container instance created.")

        # 3e. Add new desktop integration
        if do_reintegrate:
            log_verbose("-> Applying new desktop integration...")
            desktop_integration.add_desktop_integration(current_config)
            if not silent:
                print("-> Desktop integration applied.")

        # 4. Finalize state
        log_verbose("-> Finalizing new configuration state...")
        hash_utils.save_last_applied_hashes(app_config_dir, current_hashes)
        hash_utils.remove_needs_apply_flag(app_config_dir)

        if not silent:
            print("\n✅ Apply complete. Changes have been applied.")

    except Exception as e:
        print(f"❌ An unexpected error occurred during apply: {e}")
        # Mark as still needing apply
        if 'app_config_dir' in locals():
            hash_utils.create_needs_apply_flag(app_config_dir)
        sys.exit(1)