# debox/commands/run_cmd.py

import getpass
import os
import subprocess
import shlex
import sys
from debox.core import podman_utils
from debox.core import config as config_utils
from debox.core.log_utils import log_debug, log_error

def run_app(container_name: str, app_command_and_args: list[str]):
    """
    Ensures the container is running, then executes a command.
    - If 'app_command_and_args' is provided (via '--'), it's executed.
    - If 'app_command_and_args' is empty, 'runtime.default_exec' from config is used.
    It then stops the container on application exit.
    """
            
    try:
        host_user = getpass.getuser()
        log_debug(f"-> Running as user: {host_user}")

        # --- 1. Load Config ---
        config = {}
        try:
            config_path = config_utils.get_app_config_dir(container_name, create=False) / "config.yml"
            if not config_path.is_file():
                log_error(f"Configuration file not found for '{container_name}'.", exit_program=True)
            config = config_utils.load_config(config_path)
        except Exception as e:
            log_error(f"Loading config file {config_path} failed: {e}", exit_program=True)

        # --- 2. Determine Command to Run ---
        runtime_cfg = config.get('runtime', {})
        prepend_args = runtime_cfg.get('prepend_exec_args', [])
        
        command_to_run_parts = [] # This will hold the command and its args

        if app_command_and_args:
            # Case 1: User provided a command via '--'
            # e.g., debox run debox-libreoffice -- libreoffice --writer
            log_debug(f"-> Using command provided via CLI: {' '.join(app_command_and_args)}")
            command_to_run_parts = app_command_and_args
        else:
            # Case 2: User did NOT provide a command
            # e.g., debox run debox-vscode
            log_debug("-> No command provided via CLI, looking for 'runtime.default_exec'...")
            default_exec_string = runtime_cfg.get('default_exec')
            
            if not default_exec_string:
                log_error(f"❌ Error: 'runtime.default_exec' is not defined in config for '{container_name}'.", exit_program=True)
            
            log_debug(f"-> Using default command from config: '{default_exec_string}'")
            command_to_run_parts = shlex.split(default_exec_string)

        # --- 3. Start Container ---
        log_debug(f"-> Starting container '{container_name}' if not running...")
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
        
        log_debug(f"-> Executing command: {' '.join(exec_command)}") 
        
        app_process = subprocess.run(exec_command, check=False) 
        log_debug(f"-> Application exited with code: {app_process.returncode}")

        # --- 5. Stop Container ---
        log_debug(f"-> Stopping container '{container_name}'...")
        podman_utils.run_command(["podman", "stop", "--time=2", container_name]) 
        log_debug(f"-> Container '{container_name}' stopped.")

    except Exception as e:
        log_error(f"Running the application failed: {e}")
        try:
            log_debug(f"-> Attempting to stop container '{container_name}' after error...")
            podman_utils.run_command(["podman", "stop", "--ignore", "--time=2", container_name])
        except Exception as stop_e:
            log_error(f"-> Stopping container after previous error failed: {stop_e}")
        sys.exit(1)