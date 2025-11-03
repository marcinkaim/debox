# debox/core/podman_utils.py

import subprocess
import json
from typing import Optional, Dict
from pathlib import Path

from debox.core import state

def run_command(command: list[str], input_str: str = None, capture_output: bool = False, check: bool = True, verbose: bool = None):
    """
    A helper function to run external commands, like podman.
    """
    # Determine verbosity
    if verbose is None:
        is_verbose = state.state.verbose # Use global state
    else:
        is_verbose = verbose # Use explicitly passed value

    if is_verbose:
        print(f"--> Running command: {' '.join(command)}")

    # Determine stdout/stderr handling
    stdout_pipe = None if is_verbose else subprocess.DEVNULL
    stderr_pipe = None if is_verbose else subprocess.DEVNULL
    
    if capture_output: # capture_output always overrides silencing
        stdout_pipe = subprocess.PIPE
        stderr_pipe = subprocess.PIPE

    process = subprocess.run(
        command,
        input=input_str,
        text=True,
        check=check,
        stdout=stdout_pipe,
        stderr=stderr_pipe
    )

    if capture_output:
        return process.stdout.strip()
    
    return None

def build_image(containerfile_content: str, tag: str, context_dir: Path, 
                build_args: Optional[Dict[str, str]] = None, 
                labels: Optional[Dict[str, str]] = None): # Add labels param
    """
    Builds a container image, optionally adding labels.
    """
    command = ["podman", "build", "-f", "-", "-t", tag]

    if build_args:
        for key, value in build_args.items():
            command.extend(["--build-arg", f"{key}={value}"])

    if labels:
        for key, value in labels.items():
            command.extend(["--label", f"{key}={value}"])

    command.append(str(context_dir))

    if state.state.verbose:
        print(f"--> Running build command: {' '.join(command)}")

    process = subprocess.run(
        command,
        input=containerfile_content,
        text=True,
        check=True,
        stdout=None,
        stderr=None
    )

def create_container(name: str, image_tag: str, flags: list[str]):
    """
    Creates a container from a built image with the specified flags.
    """
    command = ["podman", "create", "--name", name] + flags + [image_tag]
    run_command(command)

def get_container_status(container_name: str) -> str:
    """
    Checks the status of a Podman container.
    """
    # Use exact name matching (^ and $) and JSON format for reliable parsing
    command = [
        "podman", "ps", "-a", 
        "--filter", f"name=^/{container_name}$", 
        "--format", "json"
    ]
    try:
        is_verbose = state.state.verbose
        if is_verbose:
            print(f"--> Running command: {' '.join(command)}")

        process = subprocess.run(
            command, 
            capture_output=True,
            text=True, 
            check=False,
        )
        
        if process.returncode != 0:
            if is_verbose:
                print(f"Warning: 'podman ps' command failed: {process.stderr.strip()}")
            return "Error"
            
        output = process.stdout.strip()
        if not output or output == '[]':
            return "Not Found"
            
        container_info_list = json.loads(output)
        if not container_info_list:
             return "Not Found"

        return container_info_list[0].get('State', 'Unknown')
    
    except json.JSONDecodeError:
        print(f"Warning: Could not parse JSON output from podman ps for {container_name}")
        return "Error (JSON)"
    except Exception as e:
        print(f"Warning: An unexpected error occurred checking status for {container_name}: {e}")
        return "Error (Check)"