# debox/commands/safe_prune_cmd.py

import subprocess
import typer # For confirmation prompt
from debox.core.log_utils import log_debug, log_error, log_info

# The label used to identify debox-managed resources
DEBOX_LABEL_FILTER = "label!=debox.managed=true"

def prune_resources(force: bool):
    """
    Clean up unused Podman resources safely.

    Executes 'podman system prune' with a filter to protect debox-managed resources.
    Removes dangling images, stopped containers, and unused networks/volumes.
    """
    log_debug("--- Starting Safe Prune Operation ---")

    # --- 1. Handle Confirmation ---
    if not force:
        log_info(f"This will remove all unused Podman data (containers, images, networks, volumes)")
        log_info(f"EXCEPT those with the label 'debox.managed=true'.")
        # Ask for confirmation. abort=True exits script if user says 'no'.
        typer.confirm("Are you sure you want to continue?", abort=True)

    # --- 2. Build the command ---
    command = [
        "podman", "system", "prune",
        "-a", # Prune all unused images
        "--volumes", # Prune unused volumes
        "--filter", DEBOX_LABEL_FILTER, # Exclude debox resources
        "-f" # Always add -f to the podman command itself
             # because we've either passed -f or received user confirmation.
    ]

    log_debug(f"-> Executing: {' '.join(command)}")
    
    # --- 3. Execute the command directly ---
    try:
        process = subprocess.run(
            command,
            check=True,
            text=True,
            stdout=None,
            stderr=None
        ) 
        log_info("\n✅ Safe prune operation completed.")
    except subprocess.CalledProcessError as e:
        log_error(f"\nSafe prune operation failed: {e}")
    except Exception as e:
        log_error(f"\nOperation failed: {e}")