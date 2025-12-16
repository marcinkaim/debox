# debox/commands/run_cmd.py

import getpass
import os
import subprocess
import shlex
import sys
from debox.core import container_ops, podman_utils
from debox.core import config_utils
from debox.core.log_utils import log_debug, log_error

def run_app(container_name: str, app_command_and_args: list[str]):
    """
    Launch an application inside its container.

    Ensures the container is running and executes the specified command (or default).
    Automatically handles TTY allocation for interactive applications and manages
    the container lifecycle (starts before execution, stops after exit).
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

        try:
            if container_ops.restore_container_from_registry(config):
                print(f"-> Auto-restoration of '{container_name}' successful. Launching...")
        except Exception as e:
            log_error(f"Failed to auto-restore container: {e}. Cannot run application.", exit_program=True)
            
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
                log_error(f"'runtime.default_exec' is not defined in config for '{container_name}'.", exit_program=True)
            
            log_debug(f"-> Using default command from config: '{default_exec_string}'")
            command_to_run_parts = shlex.split(default_exec_string)

        # --- 3. Start Container ---
        log_debug(f"-> Starting container '{container_name}' if not running...")
        podman_utils.run_command(["podman", "start", container_name])

        # --- 4. Assemble and Run Final Command ---
        executable = command_to_run_parts[0]
        executable_args = command_to_run_parts[1:]

        podman_exec_flags = ["--user", host_user]

        current_xauth = os.environ.get("XAUTHORITY")
        if current_xauth:
            podman_exec_flags.extend(["-e", f"XAUTHORITY={current_xauth}"])

        is_interactive = runtime_cfg.get('interactive', False)
        
        if is_interactive and sys.stdin.isatty() and sys.stdout.isatty():
            log_debug("-> Interactive mode enabled (-it).")
            podman_exec_flags.append("-it")
            term_env = os.environ.get("TERM", "xterm")
            podman_exec_flags.extend(["-e", f"TERM={term_env}"])
        else:
            log_debug("-> Non-interactive mode.")

        exec_command = [
            "podman", "exec"
        ] + podman_exec_flags + [
            container_name,
            executable
        ]
        exec_command.extend(prepend_args)
        exec_command.extend(executable_args)
               
        log_debug(f"-> Executing command: {' '.join(exec_command)}") 
        
        app_process = subprocess.run(exec_command, check=False) 
        log_debug(f"-> Application exited with code: {app_process.returncode}")

        # --- 5. Stop Container ---
        log_debug(f"-> Stopping container '{container_name}'...")
        podman_utils.run_command(["podman", "stop", "--time=2", container_name]) 
        log_debug(f"-> Container '{container_name}' stopped.")

        sys.exit(app_process.returncode)

    except Exception as e:
        log_error(f"Running the application failed: {e}")
        try:
            log_debug(f"-> Attempting to stop container '{container_name}' after error...")
            podman_utils.run_command(["podman", "stop", "--ignore", "--time=2", container_name])
        except Exception as stop_e:
            log_error(f"-> Stopping container after previous error failed: {stop_e}")
        sys.exit(1)