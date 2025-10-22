# debox/debox/commands/run_cmd.py

import os
import getpass
from debox.core import podman_utils
from debox.core import config as config_utils

def run_app(container_name: str, app_args: list[str]):
    """
    Ensures the container is running and then executes the main application
    binary inside it as the correct user, combining arguments from YAML
    and the command line.
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
        # Use subprocess.run directly here, as we want the app to take over the terminal
        # We don't use podman_utils.run_command because it might capture output or check errors
        # in a way that interferes with the launched GUI app.
        import subprocess
        subprocess.run(exec_command, check=False) # Use check=False

    except Exception as e:
        print(f"An error occurred while trying to run the application: {e}")