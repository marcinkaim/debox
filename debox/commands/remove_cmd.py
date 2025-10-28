# debox/debox/commands/remove_cmd.py

import shutil

from debox.core import config as config_utils
from debox.core import podman_utils
from debox.core import desktop_integration

def remove_app(container_name: str, purge_home: bool):
    """
    Finds and removes all components of a debox application,
    identified by its unique container name.
    """
    print(f"--- Removing application associated with container: {container_name} ---")

    # Load config (still needed for alias map in remove_desktop_integration)
    config = {} # Default to empty dict
    try:
        app_config_dir = config_utils.get_app_config_dir(container_name, create=False)
        config_path = app_config_dir / "config.yml"
        if config_path.is_file():
            config = config_utils.load_config(config_path)
            print(f"-> Found configuration for '{container_name}' at {config_path}")
        else:
             print(f"Warning: Configuration file not found at {config_path}. Cleanup may be partial.")
    except Exception as e:
        print(f"Warning: Could not load configuration file. Cleanup may be partial. Error: {e}")

    try:
        desktop_integration.remove_desktop_integration(container_name, config if config else {})
    except Exception as e:
         print(f"Warning: An error occurred during desktop integration cleanup: {e}")

    # --- Remove Podman resources ---
    try:
        print(f"-> Stopping container '{container_name}' (if running)...")
        # Use --ignore to avoid errors if container is already stopped or doesn't exist
        podman_utils.run_command(["podman", "stop", "--ignore", "--time=2", container_name])
        
        print(f"-> Removing container '{container_name}'...")
        # Use --ignore for safety
        podman_utils.run_command(["podman", "rm", "--ignore", container_name])
        
        image_tag = f"localhost/{container_name}:latest"
        print(f"-> Removing image '{image_tag}'...")
        # Use --ignore for safety
        podman_utils.run_command(["podman", "rmi", "--ignore", image_tag])
    except Exception as e:
        print(f"Warning: Error during Podman resource cleanup for {container_name}: {e}")

    # --- Remove Debox Configuration ---
    try:
        app_config_dir = config_utils.get_app_config_dir(container_name, create=False)
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