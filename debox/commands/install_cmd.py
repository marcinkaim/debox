# debox/commands/install_cmd.py

from pathlib import Path
import shutil
from debox.core import config as config_utils, container_ops
from debox.core import podman_utils
from debox.core import desktop_integration

def install_app(config_path: Path):
    """
    Orchestrates the installation: build image, create container, integrate desktop.
    """
    # 1. Load config and check existing container
    try:
        config = config_utils.load_config(config_path)
        container_name = config['container_name']
    except Exception as e: # Catch potential KeyError too
        print(f"Error loading or validating configuration {config_path}: {e}")
        return

    # --- Check if container already exists ---
    print(f"-> Checking status for container '{container_name}'...")
    existing_status = podman_utils.get_container_status(container_name)

    if existing_status != "Not Found" and "error" not in existing_status.lower():
        print(f"❌ Error: Container '{container_name}' already exists (Status: {existing_status}).")
        print("   If you want to reinstall, please remove the existing application first using:")
        print(f"   debox remove \"{config.get('app_name', container_name)}\"")
        return # Exit gracefully
    elif "error" in existing_status.lower():
         print(f"Warning: Could not reliably determine status for {container_name}. Proceeding with caution.")
    else:
         print(f"-> Container '{container_name}' not found. Proceeding with installation...")
    
    # 2. Prepare debox directories
    app_config_dir = config_utils.get_app_config_dir(container_name)
    try:
        shutil.copy(config_path, app_config_dir / "config.yml")
        print(f"-> Copied config to {app_config_dir}")
        # Copy keep_alive script to build context
        current_dir = Path(__file__).parent
        keep_alive_script_src = current_dir.parent / "core" / "keep_alive.py"
        if keep_alive_script_src.is_file():
            keep_alive_script_dest = app_config_dir / "keep_alive.py"
            shutil.copy(keep_alive_script_src, keep_alive_script_dest)
            print(f"-> Copied keep_alive.py to build context: {keep_alive_script_dest}")
        else:
             print("Warning: keep_alive.py not found, CMD might be missing.")
    except Exception as e:
        print(f"Error preparing config directory {app_config_dir}: {e}")
        return
    
    # --- 3. Build Image using container_ops ---
    try:
        image_tag = container_ops.build_container_image(config, app_config_dir)
    except Exception as e:
        # Build function already prints detailed error
        return # Exit if build fails

    # --- 4. Create Container using container_ops ---
    try:
        container_ops.create_container_instance(config, image_tag)
    except Exception as e:
        # Create function already prints detailed error
        # Consider cleanup: remove built image? For now, just exit.
        return

    # --- 5. Add Desktop Integration ---
    try:
        print("--- Starting desktop integration step ---")
        desktop_integration.add_desktop_integration(config)
    except Exception as e:
         print(f"Error during desktop integration: {e}")
         # Consider cleanup: remove container/image? For now, just exit.
         return

    print("\n✅ Installation complete!")
