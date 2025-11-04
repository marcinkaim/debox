# debox/debox/cli.py

import typer
from typing_extensions import Annotated
from pathlib import Path

from debox.core.log_utils import LogLevels, set_log_level

# Import the modules that will contain the logic for each command.
# We will create these files in the next steps.
from .commands import (
    install_cmd, 
    remove_cmd, 
    list_cmd, 
    run_cmd, 
    safe_prune_cmd, 
    configure_cmd,
    apply_cmd,
    network_cmd
)

def main_callback(
    verbose: Annotated[bool, typer.Option(
        "--verbose", "-v", 
        help="Show detailed technical (DEBUG) log messages."
    )] = False,
    quiet: Annotated[bool, typer.Option(
        "--quiet", "-q",
        help="Show only WARNING and ERROR messages."
    )] = False
):
    """
    Main callback to set global flags like log level.
    """
    if verbose:
        set_log_level(LogLevels.DEBUG)
    elif quiet:
        set_log_level(LogLevels.WARNING)
    else:
        set_log_level(LogLevels.INFO)

app = typer.Typer(
    help="A container manager for desktop applications on Debian, powered by Podman.",
    callback=main_callback
)

@app.command()
def install(
    # The validation logic (exists=True, etc.) stays inside typer.Argument.
    config_file: Annotated[Path, 
                           typer.Argument(exists=True, file_okay=True, dir_okay=False, 
                                          readable=True, help="Path to the application's .yml configuration file.")]
):
    """
    Builds, creates, and integrates an application from a config file.
    """
    install_cmd.install_app(config_file)

@app.command()
def remove(
    container_name: Annotated[str, typer.Argument(help="The unique container name to remove (e.g., 'debox-firefox'). Use 'debox list' to see names.")],
    purge_home: Annotated[bool, typer.Option("--purge", help="Also remove the application's isolated home directory.")] = False
):
    """
    Removes an application's container, image, and desktop integration.
    By default, keeps the isolated home directory unless --purge is used.
    """
    # Pass the flag to the backend function
    remove_cmd.remove_app(container_name, purge_home)

@app.command(name="list") # Use 'name' to avoid conflict with the Python keyword 'list'
def list_apps():
    """
    Lists all installed debox applications and their status.
    """
    list_cmd.list_installed_apps()

@app.command()
def run(
    app_name: Annotated[str, typer.Argument(help="The name of the application container (e.g., 'debox-vscode').")],
    # Capture extra arguments passed after app_name
    app_args: Annotated[list[str], typer.Argument(help="Arguments to pass to the application inside the container.",
                                                   hidden=True)] = None # 'hidden=True' hides it from --help
):
    """
    Launches an application inside its container, passing extra arguments.
    """
    # Pass the collected arguments to the backend function
    run_cmd.run_app(app_name, app_args if app_args else [])

@app.command("safe-prune")
def safe_prune(
    force: Annotated[bool, typer.Option("-f", "--force", help="Do not prompt for confirmation.")] = False
):
    """
    Removes unused Podman data (containers, images, networks, volumes)
    EXCEPT for those managed by debox (labeled 'debox.managed=true').
    """
    safe_prune_cmd.prune_resources(force)

@app.command()
def configure(
    container_name: Annotated[str, typer.Argument(help="The unique container name to configure (e.g., 'debox-firefox').")],
    config_updates: Annotated[list[str], typer.Argument(help="Configuration updates in 'section.key:value' or 'section.key:action:value' format.")]
):
    """
    Modifies the configuration for an installed application.
    Changes must be applied with 'debox apply'.
    """
    configure_cmd.configure_app(container_name, config_updates)

@app.command()
def apply(
    container_name: Annotated[str, typer.Argument(help="The unique container name to apply changes to.")]
):
    """
    Applies any pending configuration changes made via 'debox configure'.
    This may rebuild the image and/or recreate the container.
    """
    apply_cmd.apply_changes(container_name)

network_app = typer.Typer(help="Statically configure container network access (requires container recreate).")
app.add_typer(network_app, name="network")

@network_app.command("allow")
def network_allow(
    container_name: Annotated[str, typer.Argument(help="The unique container name to reconfigure.")]
):
    """
    Sets 'permissions.network: true' in config and applies the change.
    This will recreate the container.
    """
    network_cmd.allow_network(container_name)

@network_app.command("deny")
def network_deny(
    container_name: Annotated[str, typer.Argument(help="The unique container name to reconfigure.")]
):
    """
    Sets 'permissions.network: false' in config and applies the change.
    This will recreate the container.
    """
    network_cmd.deny_network(container_name)

if __name__ == "__main__":
    app()