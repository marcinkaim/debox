# debox/core/podman_utils.py

import subprocess
import json
from typing import Optional, Dict
from pathlib import Path

from debox.core import log_utils
from debox.core.log_utils import log_debug, log_error, log_warning, console, LogLevels

def run_command(command: list[str], input_str: str = None, capture_output: bool = False, check: bool = True):
    """
    A helper function to run external commands, like podman.
    Respects the global log level for printing output.
    """
    log_debug(f"--> Running command: {' '.join(command)}")

    stdout_pipe = None
    stderr_pipe = None
    
    if capture_output:
        stdout_pipe = subprocess.PIPE
        stderr_pipe = subprocess.PIPE
    elif log_utils.CURRENT_LOG_LEVEL > LogLevels.DEBUG:
        stdout_pipe = subprocess.DEVNULL
        stderr_pipe = subprocess.DEVNULL

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
                labels: Optional[Dict[str, str]] = None):
    """
    Builds a container image.
    - In VERBOSE (DEBUG) mode, streams all output to console.
    - In SILENT (INFO) mode, logs output to a file, and prints the log ONLY if an error occurs.
    """
    command = ["podman", "build", "--pull", "-f", "-", "-t", tag]
    
    if build_args:
        for key, value in build_args.items():
            command.extend(["--build-arg", f"{key}={value}"])

    if labels:
        for key, value in labels.items():
            command.extend(["--label", f"{key}={value}"])

    command.append(str(context_dir))

    if log_utils.CURRENT_LOG_LEVEL <= LogLevels.DEBUG:
        log_debug(f"--> Running build command (verbose): {' '.join(command)}")
        subprocess.run(
            command,
            input=containerfile_content,
            text=True, 
            check=True, 
            stdout=None,
            stderr=None
        )
    else:
        log_file_path = context_dir / "build.log"
        
        try:
            with open(log_file_path, 'w') as log_file:
                process = subprocess.run(
                    command,
                    input=containerfile_content,
                    text=True,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    check=False
                )

            if process.returncode != 0:
                console.print(f"\n❌ [bold red]Build failed! (Exit code {process.returncode})[/bold red]", style="bold red")
                print(f"   Displaying build log from: {log_file_path}\n")
                print("--- BEGIN BUILD LOG ---")
                with open(log_file_path, 'r') as log_file:
                    print(log_file.read())
                print("--- END BUILD LOG ---")

                raise subprocess.CalledProcessError(process.returncode, command, output=process.stdout, stderr=process.stderr)
            else:
                log_file_path.unlink()

        except subprocess.CalledProcessError as e:
            raise e
        except Exception as e:
            log_error(f"An unexpected error occurred during build: {e}", exit_program=True)

def create_container(name: str, image_tag: str, flags: list[str]):
    """
    Creates a container from a built image with the specified flags.
    """
    command = ["podman", "create", "--name", name] + flags + [image_tag]
    run_command(command)

def local_image_exists(image_tag: str) -> bool:
    """Checks, if the image exists in local Podman cache."""
    log_debug(f"Checking for local image: {image_tag}")
    img_inspect_cmd = ["podman", "image", "inspect", image_tag]
    try:
        run_command(img_inspect_cmd, capture_output=True, check=True)
        log_debug(f"-> Local image '{image_tag}' found.")
        return True
    except Exception:
        log_debug(f"-> Local image '{image_tag}' not found.")
        return False
    
def get_container_status(container_name: str) -> str:
    """
    Checks the status of a Podman container.
    (Silent by default)
    """
    command = [
        "podman", "ps", "-a", 
        "--filter", f"name=^/{container_name}$", 
        "--format", "json"
    ]
    try:
        is_verbose = (log_utils.CURRENT_LOG_LEVEL <= LogLevels.DEBUG)
        
        if is_verbose:
            log_debug(f"--> Running command: {' '.join(command)}")

        process = subprocess.run(
            command, 
            capture_output=True,
            text=True, 
            check=False,
        )
        
        if process.returncode != 0:
            log_debug(f"Warning: 'podman ps' command failed: {process.stderr.strip()}")
            return "Error"
            
        output = process.stdout.strip()
        if not output or output == '[]':
            image_tag = f"localhost/{container_name}:latest"
            if local_image_exists(image_tag):
                return "Not Found (Image Exists)"
            else:
                return "Not Found (No Image)"
            
        container_info_list = json.loads(output)
        if not container_info_list:
            image_tag = f"localhost/{container_name}:latest"
            if local_image_exists(image_tag):
                return "Not Found (Image Exists)"
            else:
                return "Not Found (No Image)"

        return container_info_list[0].get('State', 'Unknown')

    except json.JSONDecodeError:
        log_warning(f"Could not parse JSON output from podman ps for {container_name}")
        return "Error (JSON)"
    except Exception as e:
        log_warning(f"An unexpected error occurred checking status for {container_name}: {e}")
        return "Error (Check)"