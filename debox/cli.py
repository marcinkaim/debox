# debox/debox/cli.py

from typing import Optional
import typer
from typing_extensions import Annotated
from pathlib import Path

from debox.commands import image_cmd
from debox.core import autocompletion
from debox.core.autocompletion import (
    complete_container_names, 
    complete_config_keys, 
    complete_boolean_values,
    LIST_KEYS, MAP_KEYS, BOOLEAN_KEYS
)
from debox.core.log_utils import LogLevels, log_error, set_log_level
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
        help="Enable verbose output with detailed technical logs."
    )] = False,
    quiet: Annotated[bool, typer.Option(
        "--quiet", "-q",
        help="Suppress all output except errors and warnings."
    )] = False
):
    """
    Debox: A container-based desktop application manager for Debian.
    """
    if verbose:
        set_log_level(LogLevels.DEBUG)
    elif quiet:
        set_log_level(LogLevels.WARNING)
    else:
        set_log_level(LogLevels.INFO)

app = typer.Typer(
    help="Manage desktop applications in isolated Podman containers.",
    callback=main_callback,
    add_completion=True
)

@app.command()
def install(
    container_name: Annotated[Optional[str], typer.Argument(
        help="The unique name for the new container (e.g., 'debox-firefox'). Optional if --config is used.",
        autocompletion=autocompletion.complete_container_names,
        show_default=False
    )] = None,
    config_file: Annotated[Optional[Path], typer.Option(
        "--config", "-c",
        help="Path to the YAML configuration file. Required for new installations.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True
    )] = None
):
    """
    Install a new application or re-run installation for an existing one.
    
    If the application is already installed, this command checks if the configuration matches.
    """
    if not container_name and not config_file:
        log_error("You must provide a container name, a --config file, or both.")
        raise typer.Exit(code=1)
        
    install_cmd.install_app(container_name, config_file)

@app.command()
def remove(
    container_name: Annotated[str, typer.Argument(
        help="The unique name of the container to remove.",
        autocompletion=autocompletion.complete_container_names
    )],
    purge_home: Annotated[bool, typer.Option(
        "--purge", 
        help="Delete the configuration directory, isolated home directory, and registry backup."
    )] = False
):
    """
    Remove an application and its resources.
    
    By default, preserves user data and configuration. Use --purge to delete everything.
    """
    remove_cmd.remove_app(container_name, purge_home)

@app.command("reinstall")
def reinstall(
     container_name: Annotated[str, typer.Argument(
        help="The unique name of the container to reinstall.",
        autocompletion=autocompletion.complete_container_names
    )],
    config_file: Annotated[Optional[Path], typer.Option(
        "--config", "-c",
        help="Path to a new configuration file to replace the existing one.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True
    )] = None
):
    """
    Reinstall an application from scratch.
    
    This removes the existing container and image, then installs it again using the 
    current (or provided) configuration. Preserves user data in the home directory.
    """
    reinstall_cmd.reinstall_app(container_name, config_file)

@app.command("repair")
def repair(
     container_name: Annotated[str, typer.Argument(
        help="The unique name of the container to repair.",
        autocompletion=autocompletion.complete_container_names
    )]
):
    """
    Repair an application installation.
    
    Recreates the container instance and re-applies desktop integration without 
    rebuilding the image. Useful for fixing broken shortcuts or permissions.
    """
    repair_cmd.repair_app(container_name)

@app.command(name="list") 
def list_apps():
    """
    List all installed applications and their status.
    """
    list_cmd.list_installed_apps()

@app.command()
def run(
    container_name: Annotated[str, typer.Argument(
        help="The unique name of the container to run.",
        autocompletion=complete_container_names
    )],
    app_command_and_args: Annotated[list[str], typer.Argument(
        help="Command and arguments to execute inside the container. If empty, uses the default command.",
        hidden=True
    )] = None
):
    """
    Launch an application inside its container.
    """
    run_cmd.run_app(container_name, app_command_and_args if app_command_and_args else [])

@app.command("safe-prune")
def safe_prune(
    force: Annotated[bool, typer.Option("-f", "--force", help="Skip confirmation prompt.")] = False
):
    """
    Clean up unused Podman resources.
    
    Removes dangling images, stopped containers, and networks, but preserves 
    resources managed by debox (labeled 'debox.managed=true').
    """
    safe_prune_cmd.prune_resources(force)

@app.command()
def configure(
    container_name: Annotated[str, typer.Argument(
        help="The unique name of the container to configure.",
        autocompletion=complete_container_names
    )],
    key: Annotated[str, typer.Option(
        "--key", "-k",
        help="The configuration key to modify (e.g., 'permissions.network').",
        autocompletion=complete_config_keys
    )],
    set_value: Annotated[str, typer.Option(
        "--set", "-s",
        help="Set a value.",
        autocompletion=complete_boolean_values
    )] = None,
    add_value: Annotated[str, typer.Option(
        "--add",
        help="Add a value to a list."
    )] = None,
    remove_value: Annotated[str, typer.Option(
        "--remove", "-r",
        help="Remove a value from a list."
    )] = None,
    map_value: Annotated[str, typer.Option(
        "--map", "-m",
        help="Set a key-value pair in a map."
    )] = None,
    unmap_key: Annotated[str, typer.Option(
        "--unmap", "-u",
        help="Remove a key from a map."
    )] = None
):
    """
    Modify the configuration of an installed application.
    
    Changes are staged and must be applied using 'debox apply'.
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

    # Basic validation
    if key in LIST_KEYS and action_name not in ("add", "remove"):
        log_error(f"Action '--{action_name}' is invalid for list key '{key}'. Use --add or --remove.", exit_program=True)
    if key in MAP_KEYS and action_name not in ("set_map", "unset_map"):
        log_error(f"Action '--{action_name}' is invalid for map key '{key}'. Use --map or --unmap.", exit_program=True)
    if key in BOOLEAN_KEYS and action_name != "set":
        log_error(f"Action '--{action_name}' is invalid for boolean/simple key '{key}'. Use --set.", exit_program=True)
    if action_name == "unmap": 
        action_name = "unset_map"
    
    configure_cmd.configure_app(container_name, key, value, action_name)
    
@app.command()
def apply(
    container_name: Annotated[str, typer.Argument(
        help="The unique name of the container to apply changes to.",
        autocompletion=complete_container_names
    )]
):
    """
    Apply pending configuration changes.
    
    Detects changes made by 'debox configure' and rebuilds the image or recreates 
    the container as necessary.
    """
    apply_cmd.apply_changes(container_name)

@app.command()
def upgrade(
    container_name: Annotated[str, typer.Argument(
        help="The unique name of the container to upgrade.",
        autocompletion=autocompletion.complete_container_names
    )]
):
    """
    Upgrade system packages inside the container.
    
    Runs 'apt upgrade' inside the container, commits the changes, and pushes 
    the updated image to the registry. Does not change the configuration.
    """
    upgrade_cmd.upgrade_app(container_name)


# --- Subcommand Groups ---

network_app = typer.Typer(help="Manage container network connectivity.")
app.add_typer(network_app, name="network")

@network_app.command("allow")
def network_allow(
    container_name: Annotated[str, typer.Argument(
        help="The unique name of the container.",
        autocompletion=complete_container_names
    )]
):
    """
    Enable network access for an application (recreates container).
    """
    network_cmd.allow_network(container_name)

@network_app.command("deny")
def network_deny(
    container_name: Annotated[str, typer.Argument(
        help="The unique name of the container.",
        autocompletion=complete_container_names
    )]
):
    """
    Disable network access for an application (recreates container).
    """
    network_cmd.deny_network(container_name)

system_app = typer.Typer(help="Manage the debox system environment.")
app.add_typer(system_app, name="system")

@system_app.command("setup-registry")
def setup_registry():
    """
    Initialize the local image registry.
    
    Creates the registry container, storage volume, and configures Podman to trust it.
    Safe to run multiple times.
    """
    system_cmd.setup_registry()

image_app = typer.Typer(help="Manage local images and the internal registry.")
app.add_typer(image_app, name="image")

@image_app.command("push")
def image_push(
    container_name: Annotated[str, typer.Argument(
        help="The name of the container (e.g., 'debox-firefox') to backup.",
        autocompletion=autocompletion.complete_container_names
    )]
):
    """
    Backup a local application image to the internal registry.
    """
    image_cmd.push_image(container_name)

@image_app.command("list")
def image_list():
    """
    List images stored in the internal registry.
    """
    image_cmd.list_images()

@image_app.command("rm")
def image_rm(
    image_name: Annotated[str, typer.Argument(
        help="The name of the image in the registry.",
    )],
    tag: Annotated[str, typer.Argument(
        help="The tag to remove."
    )] = "latest"
):
    """
    Remove an image from the internal registry.
    """
    image_cmd.remove_image_from_registry(image_name, tag)

@image_app.command("pull")
def image_pull(
    image_name: Annotated[str, typer.Argument(
        help="The name of the image to pull (e.g. 'debox-firefox')."
    )]
):
    """
    Restore an image from the internal registry to the local Podman cache.
    """
    image_cmd.pull_image(image_name)

@image_app.command("prune")
def image_prune(
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Simulate the cleanup without deleting data.")] = False
):
    """
    Clean up unused data in the internal registry.
    """
    image_cmd.prune_registry(dry_run)

@image_app.command("restore")
def image_restore(
    container_name: Annotated[Optional[str], typer.Argument(
        help="The specific container name to restore.",
        autocompletion=autocompletion.complete_container_names
    )] = None,
    all_apps: Annotated[bool, typer.Option(
        "--all", "-a",
        help="Restore all configured applications."
    )] = False
):
    """
    Restore missing containers or images from the registry.
    """
    image_cmd.restore_images(container_name, all_apps)

@image_app.command("build")
def image_build(
    config_file: Annotated[Path, typer.Argument(
        help="Path to the base image configuration file.",
        exists=True, file_okay=True, dir_okay=False, readable=True
    )]
):
    """
    Build a shared base image from a configuration file.
    """
    image_cmd.build_base_image(config_file)

if __name__ == "__main__":
    app(prog_name="debox")
