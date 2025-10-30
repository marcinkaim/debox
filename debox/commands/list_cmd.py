# debox/commands/list_cmd.py

import os
from pathlib import Path
from rich.console import Console
from rich.table import Table

from debox.core import config as config_utils
from debox.core import podman_utils
# --- ADD import for the hash_utils module ---
from debox.core import hash_utils

def list_installed_apps():
    """
    Lists all applications managed by debox, their container status,
    and their configuration status.
    """
    console = Console()
    table = Table(title="Debox Managed Applications")

    # --- Define table columns (added Config Status) ---
    table.add_column("App Name", style="cyan", no_wrap=True)
    table.add_column("Container Name", style="magenta")
    table.add_column("Container Status", style="green") # Renamed from "Status"
    table.add_column("Config Status", style="yellow")   # <-- NEW COLUMN
    table.add_column("Base Image", style="blue")
    table.add_column("Config Path", style="dim")

    # Check if the main apps directory exists
    if not config_utils.DEBOX_APPS_DIR.is_dir():
        console.print(f"No debox applications installed yet (directory not found: {config_utils.DEBOX_APPS_DIR})")
        return

    found_apps = False
    # Iterate through subdirectories in the apps config directory
    for app_dir in config_utils.DEBOX_APPS_DIR.iterdir():
        if not app_dir.is_dir():
            continue # Skip non-directory files

        config_path = app_dir / "config.yml"
        if config_path.is_file():
            found_apps = True
            config_status = "[red]Error[/red]" # Default in case of error
            try:
                # Load the app configuration
                config = config_utils.load_config(config_path)
                app_name = config.get('app_name', 'N/A')
                container_name = config.get('container_name', 'N/A')
                base_image = config.get('image', {}).get('base', 'N/A')

                # Get the container status using our utility function
                container_status = podman_utils.get_container_status(container_name)

                # Add styling based on container status
                status_style = "green"
                if "run" not in container_status.lower(): # If not 'Running'
                    status_style = "yellow"
                if "not found" in container_status.lower() or "error" in container_status.lower():
                     status_style = "red"
                
                # --- Check Config Status ---
                # Check for the existence of the .needs_apply flag file
                flag_file = app_dir / hash_utils.FLAG_FILE_NAME
                if flag_file.is_file():
                    config_status = "[bold yellow]Modified[/bold yellow]"
                else:
                    config_status = "[green]Applied[/green]"
                
                # Add row to the table
                table.add_row(
                    app_name,
                    container_name,
                    f"[{status_style}]{container_status}[/{status_style}]",
                    config_status, # <-- Add new data
                    base_image,
                    str(config_path)
                )
            except Exception as e:
                # Handle cases where config file might be invalid
                table.add_row(
                    f"Error loading {app_dir.name}",
                    app_dir.name,
                    "[red]N/A[/red]",
                    "[red]Invalid Config[/red]", # Add status for error row
                    "N/A",
                    str(config_path),
                    style="on red"
                )
                print(f"Warning: Failed to load config for {app_dir.name}: {e}")

    if not found_apps:
         console.print("No debox applications installed yet.")
    else:
        # Print the final table
        console.print(table)