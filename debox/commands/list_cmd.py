# debox/commands/list_cmd.py

import os
from pathlib import Path
from rich.console import Console
from rich.table import Table

from debox.core import config as config_utils
from debox.core import podman_utils

def list_installed_apps():
    """
    Lists all applications managed by debox and their status.
    """
    console = Console()
    table = Table(title="Debox Managed Applications")

    # Define table columns
    table.add_column("App Name", style="cyan", no_wrap=True)
    table.add_column("Container Name", style="magenta")
    table.add_column("Status", style="green")
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
            try:
                # Load the app configuration
                config = config_utils.load_config(config_path)
                app_name = config.get('app_name', 'N/A')
                container_name = config.get('container_name', 'N/A')
                base_image = config.get('image', {}).get('base', 'N/A')

                # Get the container status using our new utility function
                status = podman_utils.get_container_status(container_name)

                # Add styling based on status
                status_style = "green"
                if "run" not in status.lower(): # If not 'Running'
                    status_style = "yellow"
                if "not found" in status.lower() or "error" in status.lower():
                     status_style = "red"
                
                # Add row to the table
                table.add_row(
                    app_name,
                    container_name,
                    f"[{status_style}]{status}[/{status_style}]", # Apply style
                    base_image,
                    str(config_path)
                )
            except Exception as e:
                # Handle cases where config file might be invalid
                table.add_row(
                    f"Error loading {app_dir.name}",
                    app_dir.name,
                    "[red]Invalid Config[/red]",
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