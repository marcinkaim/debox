# debox/commands/safe_prune_cmd.py

import subprocess
import typer # For confirmation prompt
from debox.core import podman_utils
from debox.core.log_utils import log_verbose, console

# The label used to identify debox-managed resources
DEBOX_LABEL_FILTER = "label!=debox.managed=true"

def prune_resources(force: bool):
    """
    Executes 'podman system prune', filtering out debox resources.
    Handles confirmation prompt internally and always shows podman output.
    """
    log_verbose("--- Starting Safe Prune Operation ---")

    # --- 1. Handle Confirmation ---
    if not force:
        console.print(f"This will remove all unused Podman data (containers, images, networks, volumes)")
        console.print(f"EXCEPT those with the label 'debox.managed=true'.")
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

    log_verbose(f"-> Executing: {' '.join(command)}")
    
    # --- 3. Execute the command directly ---
    try:
        process = subprocess.run(
            command,
            check=True,
            text=True,
            stdout=None,
            stderr=None
        ) 
        console.print("\n✅ Safe prune operation completed.")
    except subprocess.CalledProcessError as e:
        # Ten błąd wystąpi, jeśli podman zwróci kod błędu inny niż 0
        console.print(f"\n❌ Error during safe prune operation: {e}")
    except Exception as e:
        # Inne błędy, np. nie znaleziono 'podman'
        console.print(f"\n❌ An unexpected error occurred: {e}")