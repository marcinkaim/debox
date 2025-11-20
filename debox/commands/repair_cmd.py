# debox/commands/repair_cmd.py


from debox.core import podman_utils
from debox.core import hash_utils
from debox.core import container_ops
from debox.core import desktop_integration
from debox.core import config_utils
from debox.core.log_utils import log_debug, run_step, console, log_info, log_error

def repair_app(container_name: str):
    """
    Performs a repair on an existing installation by:
    1. Removing desktop integration.
    2. Removing the container instance.
    3. Creating a new container instance from the *existing* image.
    4. Re-applying desktop integration.
    """
    console.print(f"--- Repairing application: {container_name} ---", style="bold")
    
    try:
        app_config_dir = config_utils.get_app_config_dir(container_name, create=False)
        config_path = app_config_dir / "config.yml"
        
        if not config_path.is_file():
            log_error(f"Configuration file for '{container_name}' not found. Cannot repair.", exit_program=True)

        config = config_utils.load_config(config_path)
        image_tag = f"localhost/{container_name}:latest"

        log_debug(f"Checking for existing image: {image_tag}")
        try:
             podman_utils.run_command(["podman", "image", "inspect", image_tag], capture_output=True)
             log_debug("-> Image found.")
        except Exception:
             log_error(f"Image '{image_tag}' not found. Repair failed." + 
                       "\n   Run 'debox reinstall' to rebuild the image from configuration.", exit_program=True)

        with run_step(
            spinner_message="Removing old desktop integration...",
            success_message="-> Desktop integration removed.",
            error_message="Error removing old desktop integration"
        ):
            desktop_integration.remove_desktop_integration(container_name, config)
        
        with run_step(
            spinner_message="Removing old container instance...",
            success_message="-> Container instance removed.",
            error_message="Error removing container instance"
        ):
            container_ops.remove_container_instance(container_name)

        with run_step(
            spinner_message="Creating new container instance...",
            success_message="-> Container instance created.",
            error_message="Error creating container instance"
        ):
            container_ops.create_container_instance(config, image_tag)

        with run_step(
            spinner_message="Applying new desktop integration...",
            success_message="-> Desktop integration applied.",
            error_message="Error applying desktop integration"
        ):
            desktop_integration.add_desktop_integration(config)

        log_debug("-> Finalizing installation state...")
        current_hashes = hash_utils.calculate_hashes(config)
        hash_utils.save_last_applied_hashes(app_config_dir, current_hashes)
        hash_utils.set_installation_status(app_config_dir, hash_utils.STATUS_INSTALLED)
        hash_utils.remove_needs_apply_flag(app_config_dir)

        log_info(f"\n✅ Repair of '{container_name}' complete!")

    except SystemExit:
        pass
    except Exception as e:
        log_error(f"Repair failed: {e}", exit_program=True)