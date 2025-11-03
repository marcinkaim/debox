# debox/commands/install_cmd.py

from pathlib import Path
import shutil
import sys
from debox.core import config as config_utils, container_ops, hash_utils
from debox.core import podman_utils
from debox.core import desktop_integration
from debox.core.log_utils import log_verbose

def install_app(config_path: Path):
    """
    Orchestrates the installation: build image, create container, integrate desktop.
    """
    log_verbose(f"--- Starting installation from: {config_path} ---")

    # 1. Load config and check existing container
    try:
        config = config_utils.load_config(config_path)
        container_name = config['container_name']
        app_name = config.get('app_name', container_name)
    except Exception as e:
        print(f"❌ Error loading configuration {config_path}: {e}")
        sys.exit(1)

    print(f"--- Installing application: {app_name} ({container_name}) ---")

    log_verbose(f"-> Checking status for container '{container_name}'...")
    existing_status = podman_utils.get_container_status(container_name)
    if existing_status != "Not Found" and "error" not in existing_status.lower():
        print(f"❌ Error: Container '{container_name}' already exists (Status: {existing_status}).")
        print(f"   Use: debox remove {container_name}")
        sys.exit(1)

    log_verbose(f"-> Container '{container_name}' not found. Proceeding.")    

    # 2. Prepare debox directories
    app_config_dir = config_utils.get_app_config_dir(container_name)
    try:
        log_verbose("-> Preparing debox configuration directories...")
        shutil.copy(config_path, app_config_dir / "config.yml")
        log_verbose(f"-> Copied config to {app_config_dir}")

        # Copy keep_alive script to build context
        current_dir = Path(__file__).parent
        keep_alive_script_src = current_dir.parent / "core" / "keep_alive.py"
        if keep_alive_script_src.is_file():
            keep_alive_script_dest = app_config_dir / "keep_alive.py"
            shutil.copy(keep_alive_script_src, keep_alive_script_dest)
            log_verbose(f"-> Copied keep_alive.py to build context: {keep_alive_script_dest}")
        else:
            print("Warning: keep_alive.py not found, CMD might be missing.")
        
        print("-> Configuration loaded and prepared.")
    except Exception as e:
        print(f"Error preparing config directory {app_config_dir}: {e}")
        sys.exit(1)
    
    # 3. Build Image
    try:
        print(f"-> Building image... (This may take a while)")
        image_tag = container_ops.build_container_image(config, app_config_dir)
        print("-> Image built successfully.")
    except Exception as e:
        print(f"❌ Error building image: {e}")
        sys.exit(1)

    # 4. Create Container
    try:
        log_verbose("-> Creating container instance...")
        container_ops.create_container_instance(config, image_tag)
        print("-> Container created successfully.")
    except Exception as e:
         print(f"❌ Error creating container: {e}")
         sys.exit(1)

    # 5. Add Desktop Integration
    try:
        log_verbose("--- Starting desktop integration step ---")
        desktop_integration.add_desktop_integration(config)
        print("-> Desktop integration applied.")
    except Exception as e:
         print(f"❌ Error during desktop integration: {e}")
         sys.exit(1)

    # 6. Finalize installation
    try:
        log_verbose("-> Finalizing installation state...")
        current_hashes = hash_utils.calculate_hashes(config)
        hash_utils.save_last_applied_hashes(app_config_dir, current_hashes)
        hash_utils.remove_needs_apply_flag(app_config_dir) # Usuń flagę, jeśli była
        log_verbose("-> Installation state finalized.")
    except Exception as e:
        print(f"Warning: Could not finalize installation state: {e}")

    print(f"\n✅ Installation of '{app_name}' complete!")
