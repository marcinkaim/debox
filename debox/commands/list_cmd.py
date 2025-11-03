# debox/commands/list_cmd.py

from rich.table import Table

from debox.core import config as config_utils
from debox.core import podman_utils
# --- ADD import for the hash_utils module ---
from debox.core import hash_utils
from debox.core.log_utils import log_verbose, run_step, console

def list_installed_apps():
    """
    Lists all applications managed by debox, their container status,
    and their configuration status.
    """
    table = Table(title="Debox Managed Applications")

    # --- Define table columns (added Config Status) ---
    table.add_column("App Name", style="cyan", no_wrap=True)
    table.add_column("Container Name", style="magenta")
    table.add_column("Container Status", style="green")
    table.add_column("Config Status", style="yellow")
    table.add_column("Base Image", style="blue")
    table.add_column("Config Path", style="dim")

    # Check if the main apps directory exists
    if not config_utils.DEBOX_APPS_DIR.is_dir():
        console.print(f"No debox applications installed yet (directory not found: {config_utils.DEBOX_APPS_DIR})")
        return

    log_verbose("-> Pre-scanning for valid application configs...")
    app_dirs_list = []
    try:
        app_dirs_list = [
            app_dir for app_dir in config_utils.DEBOX_APPS_DIR.iterdir()
            if app_dir.is_dir() and (app_dir / "config.yml").is_file()
        ]
        total_apps = len(app_dirs_list)
        log_verbose(f"-> Found {total_apps} application(s).")
    except Exception as e:
        console.print(f"❌ Error scanning config directory: {e}", style="bold red")
        return

    if total_apps == 0:
        console.print("No debox applications installed yet.")
        return
    
    with run_step(
        spinner_message="[bold green]Loading application status...",
        success_message="",
        error_message="Error loading application list"
    ) as status:
        # Iterate through subdirectories in the apps config directory
        for i, app_dir in enumerate(app_dirs_list):
            config_path = app_dir / "config.yml"
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
                console.print(f"Warning: Failed to load config {app_dir.name}: {e}", style="yellow")
                table.add_row(
                    f"Error loading {app_dir.name}",
                    app_dir.name,
                    "[red]N/A[/red]",
                    "[red]Invalid Config[/red]", # Add status for error row
                    "N/A",
                    str(config_path),
                    style="on red"
                )
            
            percent_complete = int(((i + 1) / total_apps) * 100)
            if status: # status będzie None w trybie verbose
                status.update(f"[bold green]Loading application status... {percent_complete}%")

        # Print the final table
        console.print(table)