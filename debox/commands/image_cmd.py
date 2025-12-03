# debox/commands/image_cmd.py
"""
Handles 'debox image ...' subcommands.
"""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import typer
from typing_extensions import Annotated
from rich.table import Table
import yaml
from debox.core import config_utils, container_ops, global_config, hash_utils, registry_utils, podman_utils
from debox.core.log_utils import log_info, log_error, log_debug, console, log_warning, run_step

def push_image(container_name: str):
    """
    Pushes an existing local debox image to the local registry
    and saves the resulting digest.
    """
    log_info(f"--- Pushing image for {container_name} to local registry ---")
    image_tag_local = f"localhost/{container_name}:latest"
    
    app_config_dir = config_utils.get_app_config_dir(container_name, create=False)
    if not app_config_dir.is_dir():
        log_warning(f"Config directory not found for '{container_name}'. Cannot save digest.")
    
    log_debug(f"Checking if local image '{image_tag_local}' exists...")
    try:
         podman_utils.run_command(["podman", "image", "inspect", image_tag_local], capture_output=True, check=True)
    except Exception:
         log_error(f"Local image '{image_tag_local}' not found.", exit_program=True)
         print("   Please build or install the application first.")
         return
    
    image_digest = None
    with run_step(
        spinner_message=f"Pushing {image_tag_local}...",
        success_message="-> Image pushed to local registry.",
        error_message="Failed to push image"
    ):
        image_digest = registry_utils.push_image_to_registry(image_tag_local)
    
    if not image_digest:
        log_error("Push operation did not return a digest. State file not updated.", exit_program=True)
        return

    if app_config_dir.is_dir():
        try:
            hash_utils.save_image_digest(app_config_dir, image_digest)
            log_debug(f"-> Successfully saved digest {image_digest} to state file.")
        except Exception as e:
            log_warning(f"Failed to save image digest to state file: {e}")
    else:
        log_warning(f"Config directory not found. Digest {image_digest} was not saved.")

    console.print(f"\n✅ Image for '{container_name}' is now backed up in the registry.", style="bold green")

def list_images():
    """
    Lists all configured debox applications and their registry/install status.
    """
    log_info("--- Querying Debox Application Status ---")
    
    image_data_map = {}
    
    with run_step(
        spinner_message="Scanning local configurations...",
        success_message="-> Local configurations scanned.",
        error_message="Failed to scan configurations"
    ) as status:
        if not config_utils.DEBOX_APPS_DIR.is_dir():
            log_warning("No debox configuration directory found.")
            return

        app_dirs_list = [d for d in config_utils.DEBOX_APPS_DIR.iterdir() if d.is_dir()]

        for i, app_dir in enumerate(app_dirs_list):
            if status:
                status.update(f"[bold green]Scanning config {i+1}/{len(app_dirs_list)}...")
            
            config_path = app_dir / "config.yml"
            if config_path.is_file():
                try:
                    with open(config_path, 'r') as f: config = yaml.safe_load(f)
                    if not config or 'container_name' not in config: continue
                    
                    container_name = config['container_name']
                    container_status = podman_utils.get_container_status(container_name)
                    
                    image_data_map[container_name] = {
                        'app_name': config.get('app_name', 'N/A'),
                        'base_image': config.get('image', {}).get('base', 'N/A'),
                        'status': hash_utils.get_installation_status(app_dir),
                        'container_status': container_status,
                        'in_registry': False,
                        'container_name': container_name,
                        'tags': []
                    }
                except Exception as e:
                    log_warning(f"Failed to parse config {config_path}: {e}")

    image_names_in_registry = []
    try:
        with run_step(
            spinner_message="Querying registry catalog...",
            success_message="-> Registry catalog retrieved.",
            error_message="Failed to query registry"
        ):
            image_names_in_registry = registry_utils.get_registry_catalog()
    except SystemExit:
        log_error("Could not connect to registry.", exit_program=True)
        
    if not image_names_in_registry and not image_data_map:
        log_info("-> No Debox applications configured or images found in registry.")
        return

    with run_step(
        spinner_message="Fetching tags for images...",
        success_message="-> All tags retrieved.",
        error_message="Failed to retrieve tags"
    ) as status:
        for i, name in enumerate(image_names_in_registry):
            if status:
                status.update(f"[bold green]Checking tags for {name} ({i+1}/{len(image_names_in_registry)})...")
            
            tags = registry_utils.get_image_tags(name)
            
            if not tags:
                continue

            if name in image_data_map:
                image_data_map[name]['in_registry'] = True
                image_data_map[name]['tags'] = tags
            else:
                image_data_map[name] = {
                    'app_name': 'N/A (Orphaned Image)',
                    'base_image': 'N/A',
                    'status': 'N/A',
                    'container_status': 'N/A',
                    'in_registry': True,
                    'tags': tags,
                    'container_name': name
                }

    def sort_key(item):
        name = item.get('container_name', item.get('app_name', ''))
        
        if not item['in_registry']:
            if item['status'] == hash_utils.STATUS_INSTALLED: return (3, 1, name)
            else: return (3, 2, name)
        elif item['app_name'] == 'N/A (Orphaned Image)':
            return (2, 0, name)
        else:
            if item['status'] == hash_utils.STATUS_INSTALLED: return (1, 1, name)
            else: return (1, 2, name)
            
    table_data = sorted(image_data_map.values(), key=sort_key)

    table = Table(title="Debox Image & Application Status")
    table.add_column("Image (In Registry)", style="blue")
    table.add_column("App Name", style="cyan")
    table.add_column("Container Name", style="magenta")
    table.add_column("Container Status", style="green")
    table.add_column("Base Image", style="green")
    table.add_column("App Installed?", style="yellow")
    
    for item in table_data:
        if item['in_registry'] and item.get('tags'):
             tag = item['tags'][0]
             image_str = f"{item['container_name']}:{tag}"
        else:
             image_str = "[dim]N/A[/dim]"
        
        status_str = "N/A"
        if item['status'] == hash_utils.STATUS_INSTALLED: status_str = "[green]Yes[/green]"
        elif item['status'] == hash_utils.STATUS_NOT_INSTALLED: status_str = "[dim]No[/dim]"
        
        table.add_row(
            image_str,
            item['app_name'],
            item['container_name'],
            item['container_status'],
            item['base_image'],
            status_str
        )
    console.print(table)

def remove_image_from_registry(image_name: str, tag: str, ignore_errors: bool = False):
    """
    Implements the 3-step process to delete an image from the local registry
    using the *saved digest* from the config file.
    """
    log_info(f"--- Removing image {image_name}:{tag} from local registry ---")

    is_fatal = not ignore_errors

    digest = None
    app_config_dir = config_utils.get_app_config_dir(image_name, create=False)
    image_config_dir = config_utils.get_image_config_dir(image_name, create=False)
    
    target_dir_for_cleanup = None
    
    with run_step(
        spinner_message=f"Fetching manifest digest for {image_name}...",
        success_message="",
        error_message=f"Failed to get digest for {image_name}",
        fatal=is_fatal
    ):
        if app_config_dir.is_dir():
            digest = hash_utils.get_image_digest(app_config_dir)
            if digest:
                target_dir_for_cleanup = app_config_dir
        
        if not digest and image_config_dir.is_dir():
            digest = hash_utils.get_image_digest(image_config_dir)
            if digest:
                target_dir_for_cleanup = image_config_dir

        if not digest:
            log_warning(f"No saved digest found locally. Trying to fetch from registry API...")
            digest = registry_utils.get_image_manifest_digest(image_name, tag)
    
    if not digest:
        if ignore_errors:
            log_warning("Could not find image digest. Skipping registry cleanup.")
            return
        else:
            log_error("Could not find image digest locally or in registry. Aborting.", exit_program=True)
            return

    console.print(f"-> Found image digest: {digest[:15]}...")

    with run_step(
        spinner_message=f"Deleting manifest {digest[:15]}...",
        success_message="-> Image manifest deleted.",
        error_message="Failed to delete manifest",
        fatal=is_fatal
    ):
        registry_utils.delete_image_manifest(image_name, digest)

    with run_step(
        spinner_message="Running registry garbage collector...",
        success_message="-> Registry garbage collection complete.",
        error_message="Garbage collection failed",
        fatal=is_fatal
    ):
        registry_utils.run_registry_garbage_collector()

    if target_dir_for_cleanup:
        hash_utils.remove_image_digest(target_dir_for_cleanup)
        log_debug(f"-> Removed digest from state file in {target_dir_for_cleanup}.")

    console.print(f"\n✅ Image '{image_name}:{tag}' has been permanently removed from the registry.", style="bold green")

def pull_image(image_name_input: str):
    """
    Pulls an image from the local registry into Podman cache.
    Handles input in format 'image_name' (defaults to latest) or 'image_name:tag'.
    """
    if ":" in image_name_input:
        image_name, tag = image_name_input.split(":", 1)
    else:
        image_name = image_name_input
        tag = "latest"

    log_info(f"--- Pulling image {image_name}:{tag} from local registry ---")

    with run_step(
        spinner_message=f"Pulling {image_name}:{tag}...",
        success_message="-> Image pulled and tagged successfully.",
        error_message="Failed to pull image"
    ):
        registry_utils.pull_image_from_registry(image_name, tag)

    console.print(f"\n✅ Image '{image_name}:{tag}' is now available in local Podman cache.", style="bold green")

def prune_registry(dry_run: bool):
    """
    Cleans up the local registry storage.
    Identifies orphaned images (no matching local config) and removes them,
    then runs Garbage Collection.
    """
    log_info("--- Pruning Local Registry Storage ---")
    
    if dry_run:
        console.print("[yellow]Running in DRY-RUN mode. No data will be deleted.[/yellow]")

    active_images = set()
    
    if config_utils.DEBOX_APPS_DIR.is_dir():
        for app_dir in config_utils.DEBOX_APPS_DIR.iterdir():
            config_path = app_dir / "config.yml"
            if config_path.is_file():
                try:
                    with open(config_path, 'r') as f:
                        config = yaml.safe_load(f)
                        if config and 'container_name' in config:
                            active_images.add(config['container_name'])
                except Exception: pass
    
    if config_utils.DEBOX_IMAGES_DIR.is_dir():
        for img_dir in config_utils.DEBOX_IMAGES_DIR.iterdir():
             # Nazwa katalogu to nazwa obrazu
             active_images.add(img_dir.name)
             
    log_debug(f"Active images (from config): {active_images}")

    try:
        registry_images = registry_utils.get_registry_catalog()
    except Exception as e:
        log_error(f"Failed to list registry images: {e}", exit_program=True)
        return

    orphans_found = False

    for image_name in registry_images:
        if image_name not in active_images:
            orphans_found = True
            tags = registry_utils.get_image_tags(image_name)
            
            if not tags:
                continue

            console.print(f"-> Found orphaned image: [magenta]{image_name}[/magenta] (Tags: {', '.join(tags)})")
            
            if not dry_run:
                for tag in tags:
                    remove_image_from_registry(image_name, tag, ignore_errors=True)
            else:
                 console.print(f"   [dim](Dry run) Would remove {image_name}:{tags}[/dim]")

    if not orphans_found:
        log_info("-> No orphaned images found.")

    with run_step(
        spinner_message="Running Garbage Collector...",
        success_message="-> Garbage collection finished.",
        error_message="Registry pruning failed"
    ):
        registry_utils.run_registry_garbage_collector(dry_run)
    
    console.print("\n✅ Registry prune complete. Check logs above for details on freed space.", style="bold green")
    
    try:
        registry_dir = global_config.STORAGE_DIR
        result = subprocess.run(["du", "-sh", str(registry_dir)], capture_output=True, text=True)
        if result.returncode == 0:
             console.print(f"   Current registry size: [bold]{result.stdout.split()[0]}[/bold]")
    except Exception:
        pass

def restore_images(container_name: str = None, all_apps: bool = False):
    """
    Restores deleted containers/images from the local registry.
    Can restore a single app or all configured apps.
    """
    if not container_name and not all_apps:
        console.print("❌ Error: You must specify a container name or use --all.", style="bold red")
        return

    configs_to_restore = []

    if container_name:
        app_config_dir = config_utils.get_app_config_dir(container_name, create=False)
        config_path = app_config_dir / "config.yml"
        if not config_path.is_file():
             console.print(f"❌ Error: Configuration not found for '{container_name}'.", style="bold red")
             return
        try:
            configs_to_restore.append(config_utils.load_config(config_path))
        except Exception as e:
             console.print(f"❌ Error loading config for '{container_name}': {e}", style="bold red")
             return
    
    elif all_apps:
        log_info("--- Scanning for applications to restore ---")
        if config_utils.DEBOX_APPS_DIR.is_dir():
            for app_dir in config_utils.DEBOX_APPS_DIR.iterdir():
                if app_dir.is_dir() and (app_dir / "config.yml").is_file():
                    try:
                        configs_to_restore.append(config_utils.load_config(app_dir / "config.yml"))
                    except Exception as e:
                        log_warning(f"Skipping invalid config in {app_dir.name}: {e}")

    restored_count = 0
    for config in configs_to_restore:
        name = config.get('container_name', 'unknown')
        try:
            if container_ops.restore_container_from_registry(config):
                console.print(f"✅ Restored '{name}'.", style="green")
                restored_count += 1
            else:
                if container_name:
                    console.print(f"-> '{name}' already exists. Skipping.", style="dim")
        except Exception as e:
            console.print(f"❌ Failed to restore '{name}': {e}", style="bold red")

    if restored_count > 0:
        console.print(f"\n✅ Successfully restored {restored_count} application(s).", style="bold green")
    elif all_apps:
        console.print("\n-> No missing containers/images found.", style="dim")

def build_base_image(config_path: Path):
    """
    Builds a shared base image and pushes it to the local registry.
    """
    console.print(f"--- Building Base Image from: {config_path} ---", style="bold")

    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        if 'image_name' not in config:
            log_error("Config file must contain 'image_name' field.", exit_program=True)
        
        config['container_name'] = config['image_name']
        image_name = config['image_name']
        
    except Exception as e:
        log_error(f"Error loading configuration: {e}", exit_program=True)

    with tempfile.TemporaryDirectory() as temp_dir_str:
        temp_context_dir = Path(temp_dir_str)
        log_debug(f"-> Created temporary build context: {temp_context_dir}")

        try:
            current_dir = Path(__file__).parent
            keep_alive_script_src = current_dir.parent / "core" / "keep_alive.py"
            if keep_alive_script_src.is_file():
                shutil.copy2(keep_alive_script_src, temp_context_dir / "keep_alive.py")
                log_debug(f"-> Copied keep_alive.py to temp context.")
            
            local_debs = config.get('image', {}).get('local_debs', [])
            if local_debs:
                for deb_path_str in local_debs:
                    deb_path = Path(os.path.expanduser(deb_path_str))
                    if not deb_path.is_file():
                         raise FileNotFoundError(f"Local package not found: {deb_path}")
                    shutil.copy2(deb_path, temp_context_dir / deb_path.name)

            image_tag = f"localhost/{image_name}:latest"
            with run_step(
                spinner_message=f"Building base image '{image_tag}'...",
                success_message="-> Base image built successfully.",
                error_message="Error building base image"
            ):
                container_ops.build_container_image(config, temp_context_dir)

            with run_step(
                spinner_message="Pushing image to local registry...",
                success_message="-> Base image pushed to registry.",
                error_message="Error pushing base image"
            ):
                image_digest = registry_utils.push_image_to_registry(image_tag)

            if image_digest:
                try:
                    # Użyj nowej funkcji z config_utils
                    image_config_dir = config_utils.get_image_config_dir(image_name)
                    hash_utils.save_image_digest(image_config_dir, image_digest)
                    log_debug(f"-> Saved digest to {image_config_dir}")
                except Exception as e:
                    log_warning(f"Failed to save image digest: {e}")

        except Exception as e:
            log_error(f"Build process failed: {e}", exit_program=True)

    console.print(f"\n✅ Base image '{image_name}' is ready to use.", style="bold green")
    console.print(f"   You can now use 'base: localhost/{image_name}:latest' in your app configs.")