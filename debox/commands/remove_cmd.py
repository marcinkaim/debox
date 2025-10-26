# debox/debox/commands/remove_cmd.py

import os
import shutil
from pathlib import Path
import glob # For finding icon files with different extensions

from debox.core import config as config_utils
from debox.core import podman_utils

def remove_app(container_name: str, purge_home: bool):
    """
    Finds and removes all components of a debox application,
    identified by its unique container name.
    """
    print(f"--- Removing application associated with container: {container_name} ---")

    # --- Find the application's configuration ---
    app_config_dir = config_utils.get_app_config_dir(container_name, create=False)
    config_path = app_config_dir / "config.yml"
    config = None # Initialize config to None

    if not app_config_dir.is_dir() or not config_path.is_file():
        print(f"Error: Configuration directory or file not found for '{container_name}'.")
        # Optionally, try cleanup anyway based just on container_name?
        # For now, we exit if config is missing.
        return
    
    try:
        config = config_utils.load_config(config_path)
        print(f"-> Found configuration for '{container_name}' at {config_path}")
    except Exception as e:
        print(f"Warning: Could not load configuration file {config_path}. Proceeding with cleanup based on name only. Error: {e}")
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

    # --- Remove Desktop Integration Files ---
    try:
        desktop_files_removed_count = 0
        # --- Remove .desktop files by prefix ---
        desktop_prefix = f"{container_name}_*.desktop"
        desktop_pattern = str(config_utils.DESKTOP_FILES_DIR / desktop_prefix)
        print(f"-> Searching for desktop files matching: {desktop_pattern}")
        
        # Use glob to find all matching desktop files
        found_desktop_files = glob.glob(desktop_pattern)
        for desktop_path_str in found_desktop_files:
            desktop_path = Path(desktop_path_str)
            if desktop_path.is_file():
                print(f"--> Found and removing desktop file: {desktop_path}")
                try:
                    desktop_path.unlink()
                    desktop_files_removed_count += 1
                except OSError as e:
                    print(f"--> Warning: Could not remove desktop file {desktop_path}: {e}")

        if desktop_files_removed_count > 0:
            print(f"-> Removed {desktop_files_removed_count} desktop file(s) for '{container_name}'.")
            print("-> Updating desktop application database...")
            try: # Add try-except for robustness
                podman_utils.run_command(["update-desktop-database", str(config_utils.DESKTOP_FILES_DIR)])
            except Exception as db_e:
                    print(f"Warning: Failed to update desktop database: {db_e}")
        else:
                print(f"-> No desktop files found matching prefix '{container_name}_'.")

        # --- Remove icon files by prefix (Logic remains the same as last version) ---
        icon_prefix_pattern = f"{container_name}_*.*" 
        print(f"-> Searching for icon files starting with '{container_name}_' to remove...")
        
        icon_removed_count = 0
        user_icon_dir = Path(os.path.expanduser("~/.local/share/icons"))
        user_pixmap_dir = Path(os.path.expanduser("~/.local/share/pixmaps"))

        # Search recursively in user icons dir for the prefix pattern
        if user_icon_dir.is_dir():
            for icon_path in user_icon_dir.rglob(icon_prefix_pattern): 
                if icon_path.is_file():
                    print(f"--> Found and removing icon: {icon_path}")
                    try:
                        icon_path.unlink()
                        icon_removed_count += 1
                    except OSError as e:
                        print(f"--> Warning: Could not remove icon {icon_path}: {e}")
        
        # Search directly in user pixmaps dir for the prefix pattern
        if user_pixmap_dir.is_dir():
                for icon_path in user_pixmap_dir.glob(icon_prefix_pattern): 
                    if icon_path.is_file():
                        print(f"--> Found and removing icon: {icon_path}")
                        try:
                            icon_path.unlink()
                            icon_removed_count += 1
                        except OSError as e:
                            print(f"--> Warning: Could not remove icon {icon_path}: {e}")

        if icon_removed_count > 0:
            print(f"-> Removed {icon_removed_count} icon file(s) associated with '{container_name}'.")
            print("-> Updating icon cache...")
            try:
                podman_utils.run_command(["gtk-update-icon-cache", "-f", "-t", str(user_icon_dir)])
            except Exception as cache_e:
                    print(f"Warning: Failed to update icon cache: {cache_e}")
        else:
            print(f"-> No icon files starting with '{container_name}_' found in user directories.")

    except Exception as e:
        print(f"Warning: Error during desktop integration cleanup for {container_name}: {e}")

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