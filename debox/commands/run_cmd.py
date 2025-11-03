# debox/commands/run_cmd.py

import getpass
import os
import subprocess
import shlex
import sys
from debox.core import podman_utils, state
from debox.core import config as config_utils
from debox.core.log_utils import log_verbose

def run_app(container_name: str, app_command_and_args: list[str]):
    """
    Ensures the container is running, then executes a command.
    - If 'app_command_and_args' is provided (via '--'), it's executed.
    - If 'app_command_and_args' is empty, 'runtime.default_exec' from config is used.
    It then stops the container on application exit.
    """
            
    try:
        host_user = getpass.getuser()
        log_verbose(f"-> Running as user: {host_user}")

        # --- 1. Load Config ---
        config = {}
        try:
            config_path = config_utils.get_app_config_dir(container_name, create=False) / "config.yml"
            if not config_path.is_file():
                print(f"❌ Error: Configuration file not found for '{container_name}'.")
                sys.exit(1) # Critical error, can't proceed
            config = config_utils.load_config(config_path)
        except Exception as e:
             print(f"❌ Error loading config file {config_path}: {e}")
             sys.exit(1)

        # --- 2. Determine Command to Run ---
        runtime_cfg = config.get('runtime', {})
        prepend_args = runtime_cfg.get('prepend_exec_args', [])
        
        command_to_run_parts = [] # This will hold the command and its args

        if app_command_and_args:
            # Case 1: User provided a command via '--'
            # e.g., debox run debox-libreoffice -- libreoffice --writer
            log_verbose(f"-> Using command provided via CLI: {' '.join(app_command_and_args)}")
            command_to_run_parts = app_command_and_args
        else:
            # Case 2: User did NOT provide a command
            # e.g., debox run debox-vscode
            log_verbose("-> No command provided via CLI, looking for 'runtime.default_exec'...")
            default_exec_string = runtime_cfg.get('default_exec')
            
            if not default_exec_string:
                print(f"❌ Error: 'runtime.default_exec' is not defined in config for '{container_name}'.")
                print("   Please provide a command after '--', e.g.:")
                print(f"   debox run {container_name} -- <command_to_run>")
                return # Exit gracefully
            
            log_verbose(f"-> Using default command from config: '{default_exec_string}'")
            command_to_run_parts = shlex.split(default_exec_string)

        # --- 3. Start Container ---
        log_verbose(f"-> Starting container '{container_name}' if not running...")
        podman_utils.run_command(["podman", "start", container_name])

        # --- 4. Assemble and Run Final Command ---
        executable = command_to_run_parts[0]
        executable_args = command_to_run_parts[1:]
        
        exec_command = [
            "podman", "exec",
            "--user", host_user,
            container_name,
            executable          # e.g., 'code' or '/usr/lib/firefox-esr/firefox-esr'
        ]
        exec_command.extend(prepend_args)     # e.g., ['--ozone-platform=wayland']
        exec_command.extend(executable_args)  # e.g., [] or ['--writer']
        
        log_verbose(f"-> Executing command: {' '.join(exec_command)}") 
        
        app_process = subprocess.run(exec_command, check=False) 
        log_verbose(f"-> Application exited with code: {app_process.returncode}")

        # --- 5. Stop Container ---
        log_verbose(f"-> Stopping container '{container_name}'...")
        podman_utils.run_command(["podman", "stop", "--time=2", container_name]) 
        log_verbose(f"-> Container '{container_name}' stopped.")

    except Exception as e:
        print(f"An error occurred while trying to run the application: {e}")
        try:
            log_verbose(f"-> Attempting to stop container '{container_name}' after error...")
            podman_utils.run_command(["podman", "stop", "--ignore", "--time=2", container_name])
        except Exception as stop_e:
            print(f"-> Error stopping container after previous error: {stop_e}")