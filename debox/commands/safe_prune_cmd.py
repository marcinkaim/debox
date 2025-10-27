# debox/commands/safe_prune_cmd.py

import typer # For confirmation prompt
from debox.core import podman_utils

# The label used to identify debox-managed resources
DEBOX_LABEL_FILTER = "label!=debox.managed=true"

def prune_resources(force: bool):
    """
    Executes 'podman system prune' filtering out debox resources.
    """
    print("--- Starting Safe Prune Operation ---")
    print(f"This will remove all unused Podman data (containers, images, networks, volumes)")
    print(f"EXCEPT those with the label 'debox.managed=true'.")

    # --- Confirmation Prompt ---
    if not force:
        # Ask for confirmation before proceeding, unless -f is used
        confirm = typer.confirm("Are you sure you want to continue?", abort=True)
        # If user doesn't confirm (or uses Ctrl+C), abort=True exits the script

    # --- Build the command ---
    command = [
        "podman", "system", "prune",
        "-a", # Prune all unused images, not just dangling ones
        "--volumes", # Also prune unused volumes
        "--filter", DEBOX_LABEL_FILTER # Exclude debox resources
    ]
    
    # Add the force flag if requested by the user
    if force:
        command.append("-f") # Add podman's own force flag

    # --- Execute the command ---
    try:
        print(f"-> Executing: {' '.join(command)}")
        # We don't capture output here, let podman print directly to console
        podman_utils.run_command(command, capture_output=False) 
        print("\n✅ Safe prune operation completed.")
    except Exception as e:
        print(f"\n❌ Error during safe prune operation: {e}")