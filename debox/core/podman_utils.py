# debox/core/podman_utils.py

import subprocess
import json
from typing import Optional, Dict
from pathlib import Path

def run_command(command: list[str], input_str: str = None, capture_output: bool = False, check: bool = True):
    """
    A helper function to run external commands, like podman.
    Streams output to the console by default.
    """
    print(f"--> Running command: {' '.join(command)}")
    process = subprocess.run(
        command,
        input=input_str,
        text=True,
        capture_output=capture_output,
        check=check
    )
    if capture_output:
        return process.stdout.strip()
    return None

def build_image(containerfile_content: str, tag: str, context_dir: Path, build_args: Optional[Dict[str, str]] = None):
    """
    Builds a container image from a Containerfile string, using a specified
    directory as the build context.
    """
    command = ["podman", "build", "-f", "-", "-t", tag]
    
    # --- Add build arguments if they are provided ---
    if build_args:
        for key, value in build_args.items():
            command.extend(["--build-arg", f"{key}={value}"])

    # Append the context directory path as the last argument
    command.append(str(context_dir))

    run_command(command, input_str=containerfile_content)

def create_container(name: str, image_tag: str, flags: list[str]):
    """
    Creates a container from a built image with the specified flags.
    """
    command = ["podman", "create", "--name", name] + flags + [image_tag]
    run_command(command)

def get_container_status(container_name: str) -> str:
    """
    Checks the status of a Podman container.

    Args:
        container_name: The name of the container.

    Returns:
        The container status ('Running', 'Exited', 'Created', 'Not Found').
    """
    # Use exact name matching (^ and $) and JSON format for reliable parsing
    command = [
        "podman", "ps", "-a", 
        "--filter", f"name=^/{container_name}$", 
        "--format", "json"
    ]
    try:
        # Use subprocess directly to capture output easily
        process = subprocess.run(command, capture_output=True, text=True, check=False)
        
        if process.returncode != 0:
            # Handle podman command errors (rarely happens for 'ps')
            print(f"Warning: 'podman ps' command failed for {container_name}: {process.stderr}")
            return "Error"
            
        output = process.stdout.strip()
        if not output or output == '[]': # No container found
            return "Not Found"
            
        # Parse the JSON output (it's a list, even for one container)
        container_info_list = json.loads(output)
        if not container_info_list:
             return "Not Found"

        # Extract the state from the first (and only) container info dict
        return container_info_list[0].get('State', 'Unknown')

    except json.JSONDecodeError:
        print(f"Warning: Could not parse JSON output from podman ps for {container_name}")
        return "Error (JSON)"
    except Exception as e:
        print(f"Warning: An unexpected error occurred checking status for {container_name}: {e}")
        return "Error (Check)"