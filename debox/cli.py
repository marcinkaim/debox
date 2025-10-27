# debox/debox/cli.py

import typer
from typing_extensions import Annotated
from pathlib import Path

# Import the modules that will contain the logic for each command.
# We will create these files in the next steps.
from .commands import install_cmd, remove_cmd, list_cmd, run_cmd, safe_prune_cmd

# Create the main Typer application object.
# This object will manage all our commands.
app = typer.Typer(
    help="A container manager for desktop applications on Debian, powered by Podman."
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

if __name__ == "__main__":
    app()