# debox/core/lifecycle.py

import subprocess
import time
from debox.core import podman_utils
from debox.core.log_utils import log_debug, log_info, log_error, run_step

def run_post_install_hooks(container_name: str, config: dict):
    """
    Executes the post_install script defined in the configuration inside the container.
    Ensures the container is running before execution.
    """
    lifecycle_cfg = config.get('lifecycle', {})
    post_install_script = lifecycle_cfg.get('post_install')

    if not post_install_script:
        log_debug(f"-> No post-install hooks defined for {container_name}.")
        return

    log_info(f"-> Running post-install hooks for {container_name}...")
    
    # 1. Check if container is running, start if necessary
    status = podman_utils.get_container_status(container_name)
    was_stopped = "run" not in status.lower()

    if was_stopped:
        log_debug(f"-> Container {container_name} is stopped. Starting temporarily for hooks...")
        try:
            podman_utils.run_command(["podman", "start", container_name], check=True)
            # Give it a moment to be ready (optional, but safer)
            time.sleep(1)
        except Exception as e:
            log_error(f"Failed to start container for lifecycle hooks: {e}", exit_program=True)

    # 2. Prepare command
    command = [
        "podman", "exec", 
        "-e", "DEBIAN_FRONTEND=noninteractive",
        container_name, 
        "/bin/bash", "-c", post_install_script
    ]

    try:
        with run_step(
            spinner_message="Executing lifecycle hooks...",
            success_message="-> Lifecycle hooks executed successfully.",
            error_message="Lifecycle hooks failed"
        ):
            # Capture output so we can print it on error
            podman_utils.run_command(command, check=True, capture_output=True)
            
    except subprocess.CalledProcessError as e:
        log_error(f"Post-install script failed via Podman exec.")
        if e.stderr:
            print(f"--- Script Error Output ---\n{e.stderr}\n---------------------------")
        if e.stdout:
            print(f"--- Script Standard Output ---\n{e.stdout}\n----------------------------")
        # Ensure cleanup even on error
        if was_stopped:
            podman_utils.run_command(["podman", "stop", "--time=2", container_name], check=False)
        raise e

    # 3. Cleanup: Stop if we started it
    if was_stopped:
        log_debug(f"-> Stopping temporary container {container_name}...")
        podman_utils.run_command(["podman", "stop", "--time=2", container_name], check=False)