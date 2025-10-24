# debox/debox/commands/run_cmd.py

import getpass
from debox.core import podman_utils
from debox.core import config as config_utils
import subprocess

def run_app(container_name: str, app_args: list[str]):
    """
    Ensures the container is running, executes the main application
    binary inside it, waits for the application to exit, and then
    stops the container.
    """
    try:
        host_user = getpass.getuser()
        print(f"-> Running as user: {host_user}")

        config_path = config_utils.get_app_config_dir(container_name, create=False) / "config.yml"
        if not config_path.is_file():
            print(f"Error: Configuration for '{container_name}' not found.")
            return

        config = config_utils.load_config(config_path)
        # --- Get base binary and YAML args separately ---
        base_binary = config['export']['binary']
        yaml_args = config.get('export', {}).get('exec_args', []) # Get list or empty list
        
        print(f"-> Starting container '{container_name}' if not running...")
        podman_utils.run_command(["podman", "start", container_name])

        # Construct the final command list
        exec_command = [
            "podman", "exec",
            "--user", host_user,
            container_name,
            base_binary
        ]
        exec_command.extend(yaml_args) # Add args from YAML first
        exec_command.extend(app_args)  # Add args passed to 'debox run' (like %F)

        print(f"-> Executing command: {' '.join(exec_command)}") # For debugging

        # --- Run the application and WAIT for it to exit ---
        app_process = subprocess.run(exec_command, check=False) 
        print(f"-> Application exited with code: {app_process.returncode}")

        # --- NEW: Stop the container after the app exits ---
        print(f"-> Stopping container '{container_name}'...")
        # Use the utility function which already includes the short timeout
        podman_utils.run_command(["podman", "stop", "--time=2", container_name]) 
        print(f"-> Container '{container_name}' stopped.")

    except Exception as e:
        print(f"An error occurred while trying to run the application: {e}")
        # Optionally, try to stop the container even if exec failed
        try:
            print(f"-> Attempting to stop container '{container_name}' after error...")
            podman_utils.run_command(["podman", "stop", "--ignore", "--time=2", container_name])
        except Exception as stop_e:
            print(f"-> Error stopping container after previous error: {stop_e}")