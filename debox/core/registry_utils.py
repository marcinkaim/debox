# debox/core/registry_utils.py
"""
Utility functions for interacting with the local debox registry.
"""

import os
from pathlib import Path
import subprocess
import tempfile
import time
import requests
from typing import List, Optional
from . import podman_utils
from . import global_config
from .log_utils import log_info, log_error, log_debug, log_warning

def ensure_registry_running():
    """
    Checks if the local registry container is running.
    Starts it if 'created' or 'exited'.
    Performs a health check to ensure it's responsive.
    """
    registry_name = global_config.get_registry_name()
    log_debug(f"Ensuring registry container '{registry_name}' is running...")
    
    status = podman_utils.get_container_status(registry_name)
    log_debug(f"Registry status: {status}")
    
    if status == "Not Found":
        log_error(f"Registry container '{registry_name}' not found.", exit_program=True)
        print("   Please run 'debox system setup-registry' first.")
    
    needs_start = False
    if "running" in status.lower():
        log_debug("-> Registry is already running.")
        # Nadal wykonaj health check
    elif "exited" in status.lower() or "created" in status.lower():
        log_info("-> Registry is not running. Starting...")
        try:
            podman_utils.run_command(["podman", "start", registry_name])
            needs_start = True
        except Exception as e:
            log_error(f"Failed to start registry: {e}", exit_program=True)
    
    log_debug("-> Verifying registry is responsive...")
    registry_address = global_config.get_registry_address()
    api_url = f"http://{registry_address}/v2/" # Podstawowy endpoint V2
    
    if needs_start:
        time.sleep(1) # Daj mu 1s na start

    for i in range(10):
        try:
            response = requests.get(api_url, timeout=1)
            if response.status_code == 200 or response.status_code == 401:
                log_debug("-> Registry is responsive.")
                return True # Sukces
        except requests.ConnectionError:
            log_debug(f"   ... registry not ready yet (attempt {i+1}/10)")
            pass # Jeszcze nie gotowe
        except Exception as e:
            log_warning(f"Registry health check error: {e}")
            
        time.sleep(0.5)
        
    log_error(f"Registry container '{registry_name}' is running but did not respond at {api_url}.", exit_program=True)
    return False
    
def push_image_to_registry(image_tag_local: str) -> Optional[str]:
    """
    Tags and pushes a local image to the local debox registry.
    Returns the image digest on success, None on failure.
    
    Args:
        image_tag_local: The full local tag (e.g., 'localhost/debox-firefox:latest')
    """
    if not ensure_registry_running():
        raise Exception("Registry could not be started.")
        
    registry_address = global_config.get_registry_address()
    
    try:
        image_name_and_tag = image_tag_local.split('/', 1)[1]
    except (IndexError, AttributeError):
        log_error(f"Invalid local image tag format: '{image_tag_local}'.", exit_program=True)
        return None

    image_tag_registry = f"{registry_address}/{image_name_and_tag}"
    log_debug(f"-> Pushing image {image_tag_local} to {image_tag_registry}...")

    digest = None
    try:
        with tempfile.NamedTemporaryFile(delete=False) as tmp_digest_file:
            digest_file_path = tmp_digest_file.name
        
        command = [
            "podman", "push",
            "--digestfile", digest_file_path, # Zapisz digest tutaj
            image_tag_local,
            image_tag_registry
        ]
        
        podman_utils.run_command(command, check=True) 
        
        if Path(digest_file_path).is_file():
            digest = Path(digest_file_path).read_text().strip()
            log_debug(f"-> Image pushed. Digest: {digest}")
    
    except Exception as e:
        log_error(f"Failed to push image: {e}", exit_program=True)
        return None
    finally:
        if 'digest_file_path' in locals() and Path(digest_file_path).is_file():
            os.remove(digest_file_path)
            
    return digest
    
def get_registry_catalog() -> List[str]:
    """
    Queries the registry's /v2/_catalog endpoint to get all repository names.
    """
    if not ensure_registry_running():
        raise Exception("Registry could not be started.")
        
    registry_address = global_config.get_registry_address()
    api_url = f"http://{registry_address}/v2/_catalog"
    
    log_debug(f"Querying registry catalog: {api_url}")
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        data = response.json()
        return data.get("repositories", [])
    except Exception as e:
        log_error(f"Failed to query registry catalog: {e}", exit_program=True)
        return []

def get_image_tags(image_name: str) -> List[str]:
    """
    Queries the registry's /v2/<name>/tags/list endpoint for a specific image.
    """
    registry_address = global_config.get_registry_address()
    api_url = f"http://{registry_address}/v2/{image_name}/tags/list"

    log_debug(f"Querying tags for {image_name}: {api_url}")
    try:
        response = requests.get(api_url, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        tags = data.get("tags")
        if isinstance(tags, list):
            return tags
        else:
            return []
            
    except Exception as e:
        log_warning(f"Failed to get tags for {image_name}: {e}")
        return ["<error>"]
    
def get_image_manifest_digest(image_name: str, tag: str) -> Optional[str]:
    """
    Fetches the 'Docker-Content-Digest' for a specific image tag.
    This digest is the unique ID required for deletion.
    """
    if not ensure_registry_running():
        raise Exception("Registry could not be started.")
        
    registry_address = global_config.get_registry_address()
    api_url = f"http://{registry_address}/v2/{image_name}/manifests/{tag}"
    
    headers = {
        "Accept": "application/vnd.docker.distribution.manifest.v2+json"
    }
    
    log_debug(f"Querying HEAD {api_url} for digest...")
    try:
        response = requests.head(api_url, headers=headers, timeout=5)
        
        if response.status_code == 404:
            log_debug(f"Image {image_name}:{tag} not found in registry (404).")
            return None
        
        response.raise_for_status()
        
        digest = response.headers.get("Docker-Content-Digest")
        if digest:
            log_debug(f"-> Found digest: {digest}")
            return digest.strip()
        else:
            log_warning(f"Registry did not return 'Docker-Content-Digest' header.")
            return None
            
    except requests.exceptions.HTTPError as e:
        log_warning(f"Failed to get image manifest for {image_name}:{tag}: {e}")
        return None
    except Exception as e:
        log_error(f"Error querying registry for digest: {e}")
        return None


def delete_image_manifest(image_name: str, digest: str) -> bool:
    """
    Deletes an image manifest from the registry using its digest.
    """
    if not ensure_registry_running():
        raise Exception("Registry could not be started.")
        
    registry_address = global_config.get_registry_address()
    api_url = f"http://{registry_address}/v2/{image_name}/manifests/{digest}"
    
    log_debug(f"Sending DELETE request to {api_url}...")
    try:
        response = requests.delete(api_url, timeout=5)
        response.raise_for_status()
        log_debug(f"-> Manifest deleted (Status: {response.status_code}).")
        return True
    except Exception as e:
        log_error(f"Failed to delete manifest {digest}: {e}", exit_program=True)
        return False

def run_registry_garbage_collector(dry_run: bool = False):
    """
    Executes the garbage collector inside the registry container.
    """
    if not ensure_registry_running():
        raise Exception("Registry could not be started.")
        
    registry_name = global_config.get_registry_name()
    registry_config_path = "/etc/docker/registry/config.yml"
    
    log_debug(f"Running garbage collector on {registry_name} (Dry run: {dry_run})...")
    
    command = [
        "podman", "exec", registry_name,
        "bin/registry", "garbage-collect",
        registry_config_path,
        "--delete-untagged=true"
    ]
    
    if dry_run:
        command.append("--dry-run")

    try:
        log_info("-> Starting Registry Garbage Collection...")
        process = subprocess.run(
            command,
            check=True,
            text=True,
            stdout=None,
            stderr=None
        )
        log_debug("-> Garbage collector finished.")
    except subprocess.CalledProcessError as e:
        log_error(f"Garbage collection failed: {e}", exit_program=True)

def pull_image_from_registry(image_name: str, tag: str = "latest") -> bool:
    """
    Pulls an image from the local registry and retags it for local use.
    
    1. Pulls localhost:5000/image_name:tag
    2. Tags it as localhost/image_name:tag
    """
    if not ensure_registry_running():
        raise Exception("Registry could not be started.")

    registry_address = global_config.get_registry_address() # np. localhost:5000
    
    registry_tagged_image = f"{registry_address}/{image_name}:{tag}"
    
    local_tagged_image = f"localhost/{image_name}:{tag}"

    log_debug(f"-> Pulling {registry_tagged_image}...")
    
    pull_cmd = ["podman", "pull", "--quiet", registry_tagged_image]
    podman_utils.run_command(pull_cmd, check=True)
    
    log_debug(f"-> Retagging to {local_tagged_image}...")
    tag_cmd = ["podman", "tag", registry_tagged_image, local_tagged_image]
    podman_utils.run_command(tag_cmd, check=True)
    
    log_debug(f"-> Removing registry tag {registry_tagged_image}...")
    untag_cmd = ["podman", "rmi", registry_tagged_image]
    podman_utils.run_command(untag_cmd, check=False)
    
    return True