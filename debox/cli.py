# debox/debox/cli.py

from typing import Optional
from debox.commands import image_cmd
import typer
from typing_extensions import Annotated
from pathlib import Path

from debox.core import autocompletion
from debox.core.autocompletion import (
    complete_container_names, 
    complete_config_keys, 
    complete_boolean_values,
    LIST_KEYS, MAP_KEYS, BOOLEAN_KEYS
)
from debox.core.log_utils import LogLevels, log_error, set_log_level
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
    network_cmd,
    reinstall_cmd,
    upgrade_cmd,
    repair_cmd,
    system_cmd
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
    container_name: Annotated[Optional[str], typer.Argument(
        help="The unique container name (optional if --config is used).",
        autocompletion=autocompletion.complete_container_names,
        show_default=False
    )] = None,
    config_file: Annotated[Optional[Path], typer.Option(
        "--config", "-c",
        help="Path to the .yml config file (required for a new install).",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True
    )] = None
):
    """
    Installs a new application from a config file.
    Use 'debox apply' or 'debox reinstall' to repair/update.
    """
    
    if not container_name and not config_file:
        log_error("You must provide a container name, a --config file, or both.")
        raise typer.Exit(code=1)
        
    install_cmd.install_app(container_name, config_file)

@app.command()
def remove(
    container_name: Annotated[str, typer.Argument(
        help="The unique container name to remove.",
        autocompletion=autocompletion.complete_container_names
    )],
    # Poprawka w opisie flagi
    purge_home: Annotated[bool, typer.Option("--purge", help="Also remove the config and isolated home directory.")] = False
):
    """
    Removes container, image, and desktop integration.
    By default, keeps config and data. Use --purge to remove everything.
    """
    remove_cmd.remove_app(container_name, purge_home)

@app.command("reinstall")
def reinstall(
     container_name: Annotated[str, typer.Argument(
        help="The unique container name to reinstall.",
        autocompletion=autocompletion.complete_container_names
    )],
    config_file: Annotated[Optional[Path], typer.Option(
        "--config", "-c",
        help="Path to a new .yml config file to use for the reinstall.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True
    )] = None
):
    """
    Forces a clean reinstall (remove artifacts + install).
    Keeps the isolated home directory by default.
    Uses --config to replace the existing configuration.
    """
    reinstall_cmd.reinstall_app(container_name, config_file)

@app.command("repair")
def repair(
     container_name: Annotated[str, typer.Argument(
        help="The unique container name to repair.",
        autocompletion=autocompletion.complete_container_names
    )]
):
    """
    Repairs an installation by recreating the container and reintegrating.
    This does NOT rebuild the image or touch your data.
    """
    repair_cmd.repair_app(container_name)

@app.command(name="list") # Use 'name' to avoid conflict with the Python keyword 'list'
def list_apps():
    """
    Lists all installed debox applications and their status.
    """
    list_cmd.list_installed_apps()

@app.command()
def run(
    app_name: Annotated[str, typer.Argument(
        help="The name of the application container (e.g., 'debox-vscode').",
        autocompletion=complete_container_names
    )],
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
    container_name: Annotated[str, typer.Argument(
        help="The unique container name to configure.",
        autocompletion=complete_container_names
    )],
    key: Annotated[str, typer.Option(
        "--key", "-k",
        help="The configuration key to modify (e.g., 'permissions.network').",
        autocompletion=complete_config_keys
    )],
    
    set_value: Annotated[str, typer.Option(
        "--set", "-s",
        help="Set a simple value (string or boolean).",
        autocompletion=complete_boolean_values
    )] = None,
    
    add_value: Annotated[str, typer.Option(
        "--add",
        help="Add a value to a list (e.g., image.packages)."
    )] = None,
    
    remove_value: Annotated[str, typer.Option(
        "--remove", "-r",
        help="Remove a value from a list."
    )] = None,
    
    map_value: Annotated[str, typer.Option(
        "--map", "-m",
        help="Set a key-value pair in a map (e.g., 'firefox-esr=ff-dev')."
    )] = None,
    
    unmap_key: Annotated[str, typer.Option(
        "--unmap", "-u",
        help="Remove a key from a map."
    )] = None
):
    """
    Modifies the configuration for an installed application.
    Changes must be applied with 'debox apply'.
    """
    
    actions = {
        'set': set_value,
        'add': add_value,
        'remove': remove_value,
        'set_map': map_value,
        'unset_map': unmap_key,
    }
    
    provided_actions = [(action, value) for action, value in actions.items() if value is not None]

    if not key:
        log_error("Option '--key' / '-k' is required.", exit_program=True)
        
    if not provided_actions:
        log_error("You must provide an action: --set, --add, --remove, --map, or --unmap.", exit_program=True)
        
    if len(provided_actions) > 1:
        log_error(f"Actions are mutually exclusive. You provided: {', '.join([a[0] for a in provided_actions])}", exit_program=True)

    action_name, value = provided_actions[0]

    if key in LIST_KEYS and action_name not in ("add", "remove"):
        log_error(f"Action '--{action_name}' is invalid for list key '{key}'. Use --add or --remove.", exit_program=True)
    if key in MAP_KEYS and action_name not in ("set_map", "unmap"):
        log_error(f"Action '--{action_name}' is invalid for map key '{key}'. Use --map or --unmap.", exit_program=True)
    if key in BOOLEAN_KEYS and action_name != "set":
        log_error(f"Action '--{action_name}' is invalid for boolean/simple key '{key}'. Use --set.", exit_program=True)
    if action_name == "unmap": 
        action_name = "unset_map"
    
    configure_cmd.configure_app(container_name, key, value, action_name)
    
@app.command()
def apply(
    container_name: Annotated[str, typer.Argument(
        help="The unique container name to apply changes to.",
        autocompletion=complete_container_names
    )]
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
    container_name: Annotated[str, typer.Argument(
        help="The unique container name to reconfigure.",
        autocompletion=complete_container_names
    )]
):
    """
    Sets 'permissions.network: true' in config and applies the change.
    This will recreate the container.
    """
    network_cmd.allow_network(container_name)

@network_app.command("deny")
def network_deny(
    container_name: Annotated[str, typer.Argument(
        help="The unique container name to reconfigure.",
        autocompletion=complete_container_names
    )]
):
    """
    Sets 'permissions.network: false' in config and applies the change.
    This will recreate the container.
    """
    network_cmd.deny_network(container_name)

@app.command()
def upgrade(
    container_name: Annotated[str, typer.Argument(
        help="The unique container name to upgrade.",
        autocompletion=autocompletion.complete_container_names
    )]
):
    """
    Upgrades all packages inside a container (in-place 'apt upgrade').
    This is a fast update. Does not change configuration.
    """
    upgrade_cmd.upgrade_app(container_name)

system_app = typer.Typer(help="Manage the debox runtime environment (registry, etc.).")
app.add_typer(system_app, name="system")

@system_app.command("setup-registry")
def setup_registry():
    """
    Creates and configures a local, rootless Podman registry.
    This command is idempotent (safe to run multiple times).
    """
    system_cmd.setup_registry()

image_app = typer.Typer(help="Manage local and registry images.")
app.add_typer(image_app, name="image")

@image_app.command("push")
def image_push(
    container_name: Annotated[str, typer.Argument(
        help="The container name (e.g., 'debox-firefox') whose image you want to push.",
        autocompletion=autocompletion.complete_container_names
    )]
):
    """
    Pushes the built local image for an app to the local registry.
    """
    image_cmd.push_image(container_name)

@image_app.command("list")
def image_list():
    """
    Lists all images currently backed up in the local debox registry.
    """
    image_cmd.list_images()

@image_app.command("rm")
def image_rm(
    image_name: Annotated[str, typer.Argument(
        help="The name of the image in the registry (e.g., 'debox-firefox').",
    )],
    tag: Annotated[str, typer.Argument(
        help="The tag of the image to remove (e.g., 'latest')."
    )] = "latest"
):
    """
    Permanently deletes an image (by tag) from the local debox registry.
    """
    image_cmd.remove_image_from_registry(image_name, tag)

@image_app.command("pull")
def image_pull(
    image_name: Annotated[str, typer.Argument(
        help="The name of the image to pull (e.g. 'debox-firefox' or 'debox-firefox:latest')."
    )]
):
    """
    Restores an image from the local registry to the Podman cache.
    """
    image_cmd.pull_image(image_name)

@image_app.command("prune")
def image_prune(
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be deleted without deleting.")] = False
):
    """
    Runs Garbage Collection on the local registry to free up disk space.
    Removes unreferenced blobs and layers.
    """
    image_cmd.prune_registry(dry_run)

@image_app.command("restore")
def image_restore(
    container_name: Annotated[Optional[str], typer.Argument(
        help="The specific container to restore.",
        autocompletion=autocompletion.complete_container_names
    )] = None,
    all_apps: Annotated[bool, typer.Option(
        "--all", "-a",
        help="Restore all configured applications that are missing."
    )] = False
):
    """
    Restores missing containers/images from the registry using local config.
    """
    image_cmd.restore_images(container_name, all_apps)

@image_app.command("build")
def image_build(
    config_file: Annotated[Path, typer.Argument(
        help="Path to the .yml config file for the base image.",
        exists=True, file_okay=True, dir_okay=False, readable=True
    )]
):
    """
    Builds a shared base image from a config file and pushes it to the registry.
    """
    image_cmd.build_base_image(config_file)

if __name__ == "__main__":
    app()