# debox/commands/run_cmd.py

import getpass
import os
import subprocess # Use subprocess directly
from debox.core import podman_utils
from debox.core import config as config_utils # Keep for config access if needed later

def run_app(container_name: str, app_command_and_args: list[str]):
    """
    Ensures the container is running, then executes the command received
    from the desktop file, prepending any additional arguments specified
    in the YAML configuration, inside the container as the correct user.
    Waits for the application to exit, and then stops the container.
    """
    # Check if a command was actually provided after '--'
    if not app_command_and_args:
        print(f"Error: No command provided to run in container '{container_name}'.")
        print("   Usage from .desktop: debox run <container_name> -- <command_to_run> [args...]")
        return

    try:
        host_user = getpass.getuser()
        print(f"-> Running as user: {host_user}")

        # Load config to get additional arguments
        config = {}
        try:
            config_path = config_utils.get_app_config_dir(container_name, create=False) / "config.yml"
            if config_path.is_file():
                config = config_utils.load_config(config_path)
            else:
                 print(f"Warning: Configuration file not found at {config_path}. Cannot load additional arguments.")
        except Exception as e:
             print(f"Warning: Error loading config {config_path}. Cannot load additional arguments. Error: {e}")

        # --- Get additional args from YAML ---
        prepend_args = config.get('runtime', {}).get('prepend_exec_args', [])

        # --- Separate original command from runtime args (like %F) ---
        original_command = app_command_and_args[0]
        original_runtime_args = app_command_and_args[1:]

        print(f"-> Starting container '{container_name}' if not running...")
        podman_utils.run_command(["podman", "start", container_name])

        # Construct the final command list for podman exec
        exec_command = [
            "podman", "exec",
            "--user", host_user,
            container_name,
            # --- Assemble the command correctly ---
            original_command          # e.g., 'code' or 'libreoffice'
        ]
        exec_command.extend(prepend_args) # Add args from YAML (e.g., --ozone...)
        exec_command.extend(original_runtime_args) # Add args from .desktop (e.g., %F -> file path)

        print(f"-> Executing command: {' '.join(exec_command)}") 
        
        # Run the application and WAIT for it to exit
        # Use check=False as application exit codes are not errors for debox run
        app_process = subprocess.run(exec_command, check=False) 
        print(f"-> Application exited with code: {app_process.returncode}")

        # Stop the container after the app exits
        print(f"-> Stopping container '{container_name}'...")
        podman_utils.run_command(["podman", "stop", "--time=2", container_name]) 
        print(f"-> Container '{container_name}' stopped.")

    except Exception as e:
        print(f"An error occurred while trying to run the application: {e}")
        # Attempt to stop container after error
        try:
            print(f"-> Attempting to stop container '{container_name}' after error...")
            podman_utils.run_command(["podman", "stop", "--ignore", "--time=2", container_name])
        except Exception as stop_e:
            print(f"-> Error stopping container after previous error: {stop_e}")