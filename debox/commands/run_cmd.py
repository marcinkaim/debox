# debox/debox/commands/run_cmd.py

import os
import shlex # Import shlex
import getpass
from debox.core import podman_utils
from debox.core import config as config_utils

def run_app(container_name: str, app_args: list[str]):
    """
    Ensures the container is running and then executes the main application
    binary inside it as the correct user, forwarding any extra arguments.
    """
    try:
        host_user = getpass.getuser()
        print(f"-> Running as user: {host_user}")

        config_path = config_utils.get_app_config_dir(container_name, create=False) / "config.yml"
        if not config_path.is_file():
            print(f"Error: Configuration for '{container_name}' not found.")
            return

        config = config_utils.load_config(config_path)
        # Get the binary command string (e.g., "code --no-sandbox")
        binary_string = config['export']['binary']
        
        # --- Safely split the binary string into command + args ---
        # shlex.split handles spaces and quotes correctly
        binary_parts = shlex.split(binary_string)

        print(f"-> Starting container '{container_name}' if not running...")
        podman_utils.run_command(["podman", "start", container_name])

        # Construct the final command list
        exec_command = [
            "podman", "exec",
            "--user", host_user,
            container_name,
        ]
        # Append the parts of the binary command (e.g., 'code', '--no-sandbox')
        exec_command.extend(binary_parts)
        # Append the extra arguments passed to debox run (e.g., '%u' -> file path)
        exec_command.extend(app_args)
        
        print(f"-> Executing command: {' '.join(exec_command)}") # For debugging
        # Use subprocess.run directly here, as we want the app to take over the terminal
        # We don't use podman_utils.run_command because it might capture output or check errors
        # in a way that interferes with the launched GUI app.
        import subprocess
        subprocess.run(exec_command, check=False) # Use check=False

    except Exception as e:
        print(f"An error occurred while trying to run the application: {e}")