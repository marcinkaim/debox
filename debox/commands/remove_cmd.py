# debox/debox/commands/remove_cmd.py

import shutil

from debox.core import config as config_utils, container_ops
from debox.core import desktop_integration

def remove_app(container_name: str, purge_home: bool):
    """
    Finds and removes all components of a debox application,
    identified by its unique container name.
    """
    print(f"--- Removing application associated with container: {container_name} ---")

    # Load config (needed for desktop integration cleanup)
    config = {} 
    try:
        app_config_dir = config_utils.get_app_config_dir(container_name, create=False)
        config_path = app_config_dir / "config.yml"
        if config_path.is_file():
            config = config_utils.load_config(config_path)
            print(f"-> Found configuration for '{container_name}' at {config_path}")
        else:
             print(f"Warning: Configuration file not found. Cleanup may be partial.")
    except Exception as e:
        print(f"Warning: Could not load configuration file. Cleanup may be partial. Error: {e}")

    # --- 1. Remove Desktop Integration FIRST ---
    # Needs config for alias map, runs exec commands if needed
    try:
        desktop_integration.remove_desktop_integration(container_name, config)
    except Exception as e:
         print(f"Warning: An error occurred during desktop integration cleanup: {e}")

    # --- 2. Remove Podman Resources using container_ops ---
    try:
        # Stop and remove the container instance
        container_ops.remove_container_instance(container_name)
        # Remove the container image
        container_ops.remove_container_image(container_name)
    except Exception as e:
        print(f"Warning: Error during Podman resource cleanup for {container_name}: {e}")

    # --- 3. Remove Debox Configuration ---
    try:
        app_config_dir = config_utils.get_app_config_dir(container_name, create=False) # Get path again
        if app_config_dir.is_dir():
            print(f"-> Removing debox configuration directory: {app_config_dir}")
            shutil.rmtree(app_config_dir)
    except Exception as e:
        print(f"Warning: Error removing configuration directory for {container_name}: {e}")
        
    # --- Optionally Remove Isolated Home ---
    if purge_home:
        try:
            app_home_dir = config_utils.get_app_home_dir(container_name, create=False)
            if app_home_dir.is_dir():
                print(f"-> Purging isolated home directory: {app_home_dir}")
                shutil.rmtree(app_home_dir)
            else:
                 print("-> Isolated home directory not found (already removed?)")
        except Exception as e:
            print(f"Warning: Error purging home directory for {container_name}: {e}")
    else:
        print(f"-> Keeping isolated home directory (use --purge to remove): {config_utils.get_app_home_dir(container_name, create=False)}")
        
    print(f"\n✅ Removal associated with '{container_name}' complete.")