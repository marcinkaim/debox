# debox/debox/commands/remove_cmd.py

import os
import shutil
from pathlib import Path
import glob # For finding icon files with different extensions

from debox.core import config as config_utils
from debox.core import podman_utils

def remove_app(app_name_to_remove: str, purge_home: bool):
    """
    Finds and removes all components of a debox application.
    """
    print(f"--- Removing application: {app_name_to_remove} ---")
    
    config_path = None
    container_name = None
    
    # --- Find the application's configuration ---
    if not config_utils.DEBOX_APPS_DIR.is_dir():
        print("Error: Debox configuration directory not found. No apps installed?")
        return

    found_config = None
    for app_dir in config_utils.DEBOX_APPS_DIR.iterdir():
        if not app_dir.is_dir():
            continue
        
        current_config_path = app_dir / "config.yml"
        if current_config_path.is_file():
            try:
                config = config_utils.load_config(current_config_path)
                current_app_name = config.get('app_name', 'N/A') # Get name from config
                print(f"DEBUG: Checking config for app '{current_app_name}'...") # DEBUG line
                # Compare case-insensitively for user convenience
                if config.get('app_name', '').lower() == app_name_to_remove.lower():
                    print(f"DEBUG: Match found!") # DEBUG line
                    found_config = config
                    config_path = current_config_path
                    container_name = config.get('container_name')
                    break # Found the app, stop searching
            except Exception as e:
                print(f"Warning: Skipping invalid config file {current_config_path}: {e}")
                
    if not found_config or not container_name:
        print(f"DEBUG: No config found for '{app_name_to_remove}'. Searched {config_utils.DEBOX_APPS_DIR}") # DEBUG line
        print(f"Error: Application '{app_name_to_remove}' not found in debox configuration.")
        return

    print(f"-> Found configuration for '{container_name}' at {config_path}")

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
        # Remove .desktop file
        desktop_file_path = config_utils.DESKTOP_FILES_DIR / f"{container_name}.desktop"
        if desktop_file_path.is_file():
            print(f"-> Removing desktop file: {desktop_file_path}")
            desktop_file_path.unlink()
            # Update desktop database after removal
            print("-> Updating desktop application database...")
            podman_utils.run_command(["update-desktop-database", str(config_utils.DESKTOP_FILES_DIR)])
        else:
            print(f"-> Desktop file not found: {desktop_file_path}") # More specific message

            # --- ICON REMOVAL ---
            # Get the original icon name used during install
            # We need to re-parse the original .desktop file briefly or get it from config
            # Let's get it from the config first, falling back to binary name
            icon_name = found_config.get('export', {}).get('icon') or found_config.get('export', {}).get('binary') or container_name
            print(f"-> Searching for icon files named '{icon_name}.*' to remove...")

            icon_removed_count = 0
            # Define standard user icon/pixmap directories
            user_icon_dir = Path(os.path.expanduser("~/.local/share/icons"))
            user_pixmap_dir = Path(os.path.expanduser("~/.local/share/pixmaps"))

            # Search recursively in user icons dir
            if user_icon_dir.is_dir():
                # Use rglob to search recursively
                for icon_path in user_icon_dir.rglob(f"{icon_name}.*"):
                    if icon_path.is_file():
                        print(f"--> Found and removing icon: {icon_path}")
                        icon_path.unlink()
                        icon_removed_count += 1
            
            # Search directly in user pixmaps dir
            if user_pixmap_dir.is_dir():
                 for icon_path in user_pixmap_dir.glob(f"{icon_name}.*"):
                     if icon_path.is_file():
                         print(f"--> Found and removing icon: {icon_path}")
                         icon_path.unlink()
                         icon_removed_count += 1

            if icon_removed_count > 0:
                print(f"-> Removed {icon_removed_count} icon file(s) named '{icon_name}.*'.")
                print("-> Updating icon cache...")
                try:
                    # Update cache for the user's icon directory
                    podman_utils.run_command(["gtk-update-icon-cache", "-f", "-t", str(user_icon_dir)])
                except Exception as cache_e:
                     print(f"Warning: Failed to update icon cache: {cache_e}")
            else:
                print(f"-> No icon files named '{icon_name}.*' found in user directories.")

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
        
    print(f"\n✅ Removal of '{app_name_to_remove}' complete.")