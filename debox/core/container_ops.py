# debox/core/container_ops.py

"""
Handles core Podman operations: building images, creating containers,
and removing containers and images for debox.
"""

from pathlib import Path
import os
import locale
import getpass

from debox.core.log_utils import log_verbose

# Import necessary functions/constants from other core modules
from . import podman_utils
from . import config as config_utils

# --- Private Helper Functions (Moved from install_cmd.py) ---

def _generate_containerfile(config: dict, host_user: str, host_uid: int, host_locale: str) -> str:
    """
    Generates the content of the Containerfile based on the YAML config.
    """
    lines = [f"FROM {config['image']['base']}"]
    lines.append(f"ARG HOST_USER={host_user}")
    lines.append(f"ARG HOST_UID={host_uid}")
    lines.append(f"ARG HOST_LOCALE={host_locale}")
    lines.append("ENV DEBIAN_FRONTEND=noninteractive")

    image_cfg = config.get('image', {})

    components = image_cfg.get('debian_components', [])
    if components:
        components_str = " ".join(components)
        log_verbose(f"-> Enabling Debian components: {components_str}")
        lines.append(
            f"RUN sed -i -e 's/ main/ main {components_str}/g' /etc/apt/sources.list.d/debian.sources"
        )
    else:
        log_verbose("-> No additional Debian components requested.")

    lines.append("RUN apt-get update && apt-get install -y wget gpg sudo locales python3 && apt-get clean")

    # Locale generation
    lines.append(f"RUN sed -i -e 's/# $HOST_LOCALE UTF-8/$HOST_LOCALE UTF-8/' /etc/locale.gen")
    lines.append(f"RUN dpkg-reconfigure --frontend=noninteractive locales")
    lines.append(f"ENV LANG=$HOST_LOCALE")

    # Handle repositories
    repo_list = image_cfg.get('repositories', [])
    if repo_list:
        repo_counter = 0
        for repo in repo_list:
            repo_string = repo.get('repo_string')
            if not repo_string:
                print(f"Warning: Skipping repository entry with no 'repo_string'.")
                continue

            key_url = repo.get('key_url')
            key_path = repo.get('key_path')
            
            if key_url and key_path:
                log_verbose(f"-> Adding keyed repository: {repo_string}")
                lines.append(f"RUN mkdir -p $(dirname {key_path})")
                lines.append(f"RUN wget -qO- {key_url} | gpg --dearmor > {key_path}")
            else:
                log_verbose(f"-> Adding keyless repository: {repo_string}")
            
            list_filename = repo.get('list_filename', f"debox-repo-{repo_counter}.list")
            lines.append(f"RUN echo \"{repo_string}\" > /etc/apt/sources.list.d/{list_filename}")
            repo_counter += 1

    # Handle package installation
    packages_to_install = image_cfg.get('packages', [])
    if packages_to_install:
        packages_str = " ".join(packages_to_install)
        
        target_release = image_cfg.get('apt_target_release')
        install_cmd = "apt-get install -y"
        
        if target_release:
            log_verbose(f"-> Setting APT target release to: {target_release}")
            install_cmd += f" -t {target_release}"
            lines.append(f"RUN echo 'APT::Default-Release \"{target_release}\";' > /etc/apt/apt.conf.d/99debox-target")

        lines.append(f"RUN apt-get update && {install_cmd} {packages_str} && apt-get clean")

    # Create the user
    lines.append(f"RUN useradd -m -s /bin/bash -u $HOST_UID $HOST_USER")
    lines.append(f"RUN usermod -aG sudo $HOST_USER")
    lines.append(f'RUN echo "$HOST_USER ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers')

    # Copy keep_alive script if exists in context
    lines.append("COPY keep_alive.py /usr/local/bin/keep_alive.py")
    lines.append("RUN chmod +x /usr/local/bin/keep_alive.py")
    lines.append('CMD ["/usr/local/bin/keep_alive.py"]')

    return "\n".join(lines)

def _generate_podman_flags(config: dict) -> list[str]:
    """
    Generates the list of flags for the 'podman create' command.
    (Code is identical to the last version in install_cmd.py)
    """
    flags = []
    permissions = config.get('permissions', {})
    storage_cfg = config.get('storage', {})
    runtime_cfg = config.get('runtime', {}) # Although not used directly for flags yet
    integration_cfg = config.get('integration', {})
    container_name = config['container_name']

    log_verbose("-> Applying configuration flags:") # Renamed log message slightly

    # --- Add Labels ---
    flags.extend(["--label", "debox.managed=true"])
    flags.extend(["--label", f"debox.app.name={config.get('app_name', 'unknown')}"])
    flags.extend(["--label", f"debox.container.name={container_name}"])
    
    # --- User Namespaces ---
    flags.append("--userns=keep-id") 

    # --- Permissions Section ---
    log_verbose("   Applying permissions:")

    # Network
    net_perm = permissions.get('network', True) 
    if not net_perm:
        flags.append("--network=none")
        log_verbose("     - Network: Disabled")
    else:
        flags.append("--network=default")
        log_verbose("     - Network: Enabled (connected to 'default' CNI bridge)")

    # System D-Bus
    sys_dbus_perm = permissions.get('system_dbus', True)
    sys_dbus_socket_var = Path("/var/run/dbus/system_bus_socket")
    sys_dbus_socket_run = Path("/run/dbus/system_bus_socket")
    actual_sys_dbus_socket = None
    if sys_dbus_socket_var.is_socket():
        actual_sys_dbus_socket = sys_dbus_socket_var
    elif sys_dbus_socket_run.is_socket():
        actual_sys_dbus_socket = sys_dbus_socket_run

    if sys_dbus_perm and actual_sys_dbus_socket: # Check boolean and if socket was found
        # Use the actual found path
        flags.extend(["-v", f"{actual_sys_dbus_socket}:{actual_sys_dbus_socket}:ro"]) 
        log_verbose(f"     - System D-Bus: Enabled (read-only, socket: {actual_sys_dbus_socket})")
    else:
        log_verbose(f"     - System D-Bus: Disabled {'(socket not found at expected locations)' if sys_dbus_perm else ''}")

    # Bluetooth (Relies on System D-Bus)
    bt_perm = permissions.get('bluetooth', False)
    if bt_perm:
        if sys_dbus_perm and actual_sys_dbus_socket: log_verbose("     - Bluetooth: Enabled (via System D-Bus)")
        else: log_verbose("     - Bluetooth: Disabled (requires System D-Bus)");
    else: log_verbose("     - Bluetooth: Disabled")

    # Printers (Relies on CUPS socket)
    printer_perm = permissions.get('printers', False)
    cups_socket = Path("/run/cups/cups.sock")
    if printer_perm:
        if cups_socket.is_socket(): flags.extend(["-v", f"{cups_socket}:{cups_socket}:rw"]); log_verbose("     - Printers: Enabled (via CUPS socket)")
        else: log_verbose("     - Printers: Disabled (CUPS socket not found)")
    else: log_verbose("     - Printers: Disabled")

    # Webcam
    webcam_perm = permissions.get('webcam', False)
    if webcam_perm:
        video_devices = list(Path("/dev").glob("video*"))
        if video_devices:
            for dev in video_devices: flags.extend(["--device", str(dev)])
            log_verbose(f"     - Webcam: Enabled ({len(video_devices)} device(s))")
        else: log_verbose("     - Webcam: Disabled (no devices found)")
    else: log_verbose("     - Webcam: Disabled")

    # Microphone (Relies on Sound/Desktop Integration)
    mic_perm = permissions.get('microphone', False)
    if mic_perm: log_verbose("     - Microphone: Enabled (via session bus)") # Assume enabled if requested & integration on
    else: log_verbose("     - Microphone: Disabled")

    # Explicit Devices
    explicit_devices = permissions.get('devices', [])
    if explicit_devices:
        log_verbose("     - Explicit Devices:")
        for device in explicit_devices:
             # Add check if device exists
             if Path(device).exists(): flags.extend(["--device", device]); log_verbose(f"       - Added: {device}")
             else: log_verbose(f"       - Warning: Device '{device}' not found. Skipping.")
    else: log_verbose("     - Explicit Devices: None")

    # --- Integration Section (GPU/Sound flags depend on this) ---
    log_verbose("   Applying integration settings:")
    desktop_integration_enabled = integration_cfg.get('desktop_integration', True)
    if desktop_integration_enabled:
        log_verbose("     - Desktop Integration: Enabled")
        xdg_runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
        if not xdg_runtime_dir: log_verbose("       Warning: XDG_RUNTIME_DIR not set.")
        else: flags.extend(["-v", f"{xdg_runtime_dir}:{xdg_runtime_dir}:rw"]) # Mount session dir

        # Pass essential env vars
        essential_env_vars = ["DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR",
                              "DBUS_SESSION_BUS_ADDRESS", "PULSE_SERVER", "XDG_SESSION_TYPE"]
        for var in essential_env_vars:
             if os.environ.get(var): flags.extend(["-e", var])

        # Apply GPU based on permission AND integration flag
        gpu_perm = permissions.get('gpu', True) # Default true if integration enabled
        if gpu_perm:
             if Path("/dev/dri").exists(): flags.append("--device=/dev/dri"); log_verbose("     - GPU: Enabled")
             else: log_verbose("     - GPU: Disabled (host device /dev/dri not found)")
        else: log_verbose("     - GPU: Disabled")

        # Apply Sound based on permission AND integration flag
        sound_perm = permissions.get('sound', True) # Default true if integration enabled
        if sound_perm: log_verbose("     - Sound: Enabled (via session bus)")
        else: log_verbose("     - Sound: Disabled")
    else:
        log_verbose("     - Desktop Integration: Disabled")
        log_verbose("     - GPU: Disabled") # Force disable if integration is off
        log_verbose("     - Sound: Disabled") # Force disable if integration is off

    # --- Storage Section ---
    log_verbose("   Applying storage settings:")
    # Isolated Home (Always added)
    home_dir = config_utils.get_app_home_dir(container_name)
    flags.extend(["-v", f"{home_dir}:{os.path.expanduser('~')}:Z"])
    log_verbose(f"     - Isolated Home: {home_dir} -> ~")
    # Additional Volumes
    volumes = storage_cfg.get('volumes', [])
    if volumes:
        for volume in volumes:
            try:
                host_path, container_path = volume.split(':')
                expanded_host_path = os.path.expanduser(host_path)
                # Add check if host path exists? Maybe optional.
                flags.extend(["-v", f"{expanded_host_path}:{container_path}:Z"])
                log_verbose(f"     - Additional: {expanded_host_path} -> {container_path}")
            except ValueError:
                print(f"     - Warning: Invalid volume format: '{volume}'. Skipping.")
    else:
        log_verbose("     - Additional Volumes: None")


    log_verbose("-> Finished applying configuration flags.")
    return flags

# --- Public Functions ---

def build_container_image(config: dict, app_config_dir: Path) -> str:
    """
    Generates the Containerfile and builds the Podman image.

    Args:
        config: The loaded application configuration dictionary.
        app_config_dir: Path to the app's config dir (build context).

    Returns:
        The tag of the built image (e.g., 'localhost/container_name:latest').
    
    Raises:
        Exception: If the build fails.
    """
    container_name = config['container_name']
    image_tag = f"localhost/{container_name}:latest"
    
    log_verbose("--- Building Container Image ---")
    
    # Get host details
    host_user = getpass.getuser()
    host_uid = os.getuid()
    host_locale = "C.UTF-8"
    try:
        loc = locale.getlocale(locale.LC_CTYPE)
        host_locale = f"{loc[0]}.{loc[1]}" if loc[0] and loc[1] else "C.UTF-8"
    except Exception as e:
        print(f"Warning: Error detecting host locale ({e}), defaulting.")
    log_verbose(f"-> Using host details: User={host_user}, UID={host_uid}, Locale={host_locale}")

    # Generate Containerfile content
    containerfile = _generate_containerfile(config, host_user, host_uid, host_locale)
    (app_config_dir / "Containerfile").write_text(containerfile) # Save for reference
    log_verbose("-> Generated Containerfile.")

    # Prepare build arguments and labels
    build_args = {"HOST_USER": host_user, "HOST_UID": str(host_uid), "HOST_LOCALE": host_locale}
    image_label = {"debox.managed": "true"}

    # Execute the build
    try:
        podman_utils.build_image(
            containerfile,
            image_tag,
            context_dir=app_config_dir,
            build_args=build_args,
            labels=image_label
        )
        log_verbose(f"-> Successfully built image '{image_tag}'")
        return image_tag
    except Exception as e:
        print(f"❌ Error building image: {e}")
        raise # Re-raise the exception to signal failure

def create_container_instance(config: dict, image_tag: str):
    """
    Generates Podman flags and creates the container instance.

    Args:
        config: The loaded application configuration dictionary.
        image_tag: The tag of the image to use.

    Raises:
        Exception: If container creation fails.
    """
    container_name = config['container_name']
    log_verbose(f"--- Creating Container Instance: {container_name} ---")
    
    # Generate flags based on config
    podman_flags = _generate_podman_flags(config)
    
    # Execute container creation
    try:
        podman_utils.create_container(container_name, image_tag, podman_flags)
        log_verbose(f"-> Successfully created container '{container_name}'")
    except Exception as e:
        print(f"❌ Error creating container: {e}")
        raise # Re-raise the exception

def remove_container_instance(container_name: str):
    """
    Stops (if running) and removes the container instance.
    Ignores errors if the container doesn't exist.
    """
    log_verbose(f"-> Stopping container '{container_name}' (if running)...")
    try:
        podman_utils.run_command(["podman", "stop", "--ignore", "--time=2", container_name])
    except Exception as e:
        print(f"  Warning: Error stopping container (might be already stopped): {e}")
        
    log_verbose(f"-> Removing container '{container_name}'...")
    try:
        podman_utils.run_command(["podman", "rm", "--ignore", container_name])
        log_verbose(f"--> Container '{container_name}' removed.")
    except Exception as e:
        print(f"  Warning: Error removing container (might be already removed): {e}")

def remove_container_image(container_name: str):
    """
    Removes the container image associated with the container name.
    Ignores errors if the image doesn't exist.
    """
    image_tag = f"localhost/{container_name}:latest"
    log_verbose(f"-> Removing image '{image_tag}'...")
    try:
        podman_utils.run_command(["podman", "rmi", "--ignore", image_tag])
        log_verbose(f"--> Image '{image_tag}' removed.")
    except Exception as e:
        print(f"  Warning: Error removing image (might be already removed or in use): {e}")