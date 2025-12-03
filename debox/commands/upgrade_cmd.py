# debox/commands/upgrade_cmd.py

from debox.core import config_utils, hash_utils, podman_utils, registry_utils
from debox.core.log_utils import log_info, log_error, log_debug, log_warning, run_step

def upgrade_app(container_name: str):
    """
    Performs an in-place upgrade of all packages in the container
    and commits the result to the container image.
    Uses spinners for long-running operations in silent mode.
    """
    log_info(f"--- Starting in-place upgrade for: {container_name} ---")
    
    image_tag = f"localhost/{container_name}:latest"

    try:
        # --- 1. Start the container ---
        with run_step(
            spinner_message="Starting container...",
            success_message="-> Container started.",
            error_message="Error starting container"
        ):
            podman_utils.run_command(["podman", "start", container_name])
        
        # --- 2. Run apt update ---
        with run_step(
            spinner_message="Running 'apt-get update' (as root)...",
            success_message="-> Package lists refreshed.",
            error_message="Failed to refresh package lists (apt-get update)"
        ):
            cmd_update = ["podman", "exec", "--user", "root", container_name, "apt-get", "update", "-y"]
            podman_utils.run_command(cmd_update)

        # --- 3. Run apt upgrade ---
        with run_step(
            spinner_message="Running 'apt-get upgrade' (as root)... (This may take a while)",
            success_message="-> Packages upgraded.",
            error_message="Failed to upgrade packages (apt-get upgrade)"
        ):
            cmd_upgrade = ["podman", "exec", "--user", "root", container_name, "apt-get", "upgrade", "-y"]
            podman_utils.run_command(cmd_upgrade)

        # --- 4. Commit the changes ---
        with run_step(
            spinner_message=f"Committing changes to image: {image_tag}...",
            success_message="-> Changes committed to image.",
            error_message="Error committing changes"
        ):
            cmd_commit = ["podman", "commit", container_name, image_tag]
            podman_utils.run_command(cmd_commit)

        # --- 5. Push image to debox registry ---
        with run_step(
            spinner_message=f"Backing up upgraded image to local registry...",
            success_message="-> Upgraded image backed up.",
            error_message="Error backing up upgraded image"
        ):
            image_digest = registry_utils.push_image_to_registry(image_tag)

        if image_digest:
            app_config_dir = config_utils.get_app_config_dir(container_name)
            hash_utils.save_image_digest(app_config_dir, image_digest)

        log_info(f"\n✅ Upgrade complete. Image '{image_tag}' has been updated.")

    except SystemExit as e:
        pass
    except Exception as e:
        log_error(f"Upgrade failed: {e}", exit_program=True)
    finally:
        log_debug(f"-> Stopping container '{container_name}'...")
        try:
            podman_utils.run_command(["podman", "stop", "--time=2", container_name], check=False)
            log_debug("-> Container stopped.")
        except Exception as stop_e:
            log_warning(f"Failed to stop container after upgrade: {stop_e}")