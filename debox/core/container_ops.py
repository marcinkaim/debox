# debox/core/container_ops.py

"""
Handles core Podman operations: building images, creating containers,
and removing containers and images for debox.
"""

from pathlib import Path
import os
import locale
import getpass

from debox.core import registry_utils
from debox.core.log_utils import log_debug, log_error, log_warning

# Import necessary functions/constants from other core modules
from . import podman_utils
from . import config_utils

# --- Private Helper Functions (Moved from install_cmd.py) ---

def _generate_containerfile(config: dict, host_user: str, host_uid: int, host_locale: str) -> str:
    """
    Generates the content of the Containerfile based on the YAML config.
    Intelligently skips steps if the base image is likely already a debox image.
    """
    base_image = config['image']['base']
    
    # --- WYKRYWANIE OBRAZU BAZOWEGO DEBOX ---
    # Jeśli obraz bazowy pochodzi z localhost, zakładamy, że jest to
    # obraz zarządzany przez debox, który ma już użytkownika, locales i keep_alive.
    is_debox_base = base_image.startswith("localhost/") or base_image.startswith("localhost:5000/")

    lines = [f"FROM {base_image}"]
    lines.append(f"ARG HOST_USER={host_user}")
    lines.append(f"ARG HOST_UID={host_uid}")
    lines.append(f"ARG HOST_LOCALE={host_locale}")
    lines.append("ENV DEBIAN_FRONTEND=noninteractive")

    image_cfg = config.get('image', {})
    integration_cfg = config.get('integration', {})
    desktop_integration_enabled = integration_cfg.get('desktop_integration', True)

    permissions = config.get('permissions', {})
    host_opener_enabled = permissions.get('host_opener', False)

    if not is_debox_base:
        components = image_cfg.get('debian_components', [])
        if components:
            components_str = " ".join(components)
            log_debug(f"-> Enabling Debian components: {components_str}")
            lines.append(
                f"RUN sed -i -e 's/ main/ main {components_str}/g' /etc/apt/sources.list.d/debian.sources"
            )
        else:
            log_debug("-> No additional Debian components requested.")

        lines.append("RUN apt-get update && apt-get install -y wget gpg sudo locales python3 && apt-get clean")

        # Locale generation
        lines.append(f"RUN echo '{host_locale} UTF-8' >> /etc/locale.gen")
        lines.append("RUN locale-gen")
        lines.append(f"ENV LANG={host_locale}")
        lines.append(f"ENV LC_ALL={host_locale}")
    else:
        pass

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
                log_debug(f"-> Adding keyed repository: {repo_string}")
                lines.append(f"RUN mkdir -p $(dirname {key_path})")
                lines.append(f"RUN wget -qO- {key_url} | gpg --dearmor > {key_path}")
            else:
                log_debug(f"-> Adding keyless repository: {repo_string}")
            
            list_filename = repo.get('list_filename')
            if not list_filename:
                list_filename = f"{config['container_name']}-repo-{repo_counter}.sources"

            lines.append(f"RUN echo \"{repo_string}\" > /etc/apt/sources.list.d/{list_filename}")
            repo_counter += 1

    # Handle package installation
    packages_to_install = image_cfg.get('packages', [])

    if desktop_integration_enabled and host_opener_enabled:
        if "libglib2.0-bin" not in packages_to_install:
            packages_to_install.append("libglib2.0-bin")
        if "xdg-utils" not in packages_to_install:
            packages_to_install.append("xdg-utils")

    local_debs_to_install = []

    local_debs_config = image_cfg.get('local_debs', [])
    if local_debs_config:
        lines.append("\n# Copy local .deb packages")
        lines.append("RUN mkdir -p /tmp/debox_debs") 
        for deb_path_str in local_debs_config:
            deb_filename = Path(os.path.expanduser(deb_path_str)).name
            container_deb_path = f"/tmp/debox_debs/{deb_filename}"
            lines.append(f"COPY {deb_filename} {container_deb_path}")
            local_debs_to_install.append(container_deb_path) 

    all_packages_str = " ".join(packages_to_install + local_debs_to_install)

    if all_packages_str.strip():
        
        target_release = image_cfg.get('apt_target_release')
        install_cmd = "apt-get install -y"
        
        if target_release:
            log_debug(f"-> Setting APT target release to: {target_release}")
            install_cmd += f" -t {target_release}"
            lines.append(f"RUN echo 'APT::Default-Release \"{target_release}\";' > /etc/apt/apt.conf.d/99debox-target")

        lines.append(f"RUN apt-get update && {install_cmd} {all_packages_str} && apt-get clean && rm -rf /tmp/debox_debs /var/lib/apt/lists/*")

    if desktop_integration_enabled and host_opener_enabled:
        lines.append("\n# --- Debox Host Opener Setup ---")
        
        # 1. Skopiuj skrypt i nadaj uprawnienia
        lines.append("COPY debox-open /usr/local/bin/debox-open")
        lines.append("RUN chmod +x /usr/local/bin/debox-open")
        
        # 2. Skopiuj plik .desktop
        lines.append("RUN mkdir -p /usr/share/applications")
        lines.append("COPY debox-open.desktop /usr/share/applications/debox-open.desktop")

        # 3. Skonfiguruj MIME (to nadal musi być komenda shella)
        mime_script = """
mkdir -p /etc/xdg
echo '[Default Applications]' > /etc/xdg/mimeapps.list
echo 'text/html=debox-open.desktop' >> /etc/xdg/mimeapps.list
echo 'x-scheme-handler/http=debox-open.desktop' >> /etc/xdg/mimeapps.list
echo 'x-scheme-handler/https=debox-open.desktop' >> /etc/xdg/mimeapps.list
"""
        mime_oneline = " && ".join([line.strip() for line in mime_script.strip().splitlines() if line.strip()])
        lines.append(f"RUN {mime_oneline}")

    if not is_debox_base:
        # Create the user
        lines.append(f"RUN useradd -m -s /bin/bash -u $HOST_UID $HOST_USER")
        lines.append(f"RUN usermod -aG sudo $HOST_USER")
        lines.append(f'RUN echo "$HOST_USER ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers')

        # Copy keep_alive script if exists in context
        lines.append("COPY keep_alive.py /usr/local/bin/keep_alive.py")
        lines.append("RUN chmod +x /usr/local/bin/keep_alive.py")
        lines.append('CMD ["/usr/local/bin/keep_alive.py"]')
    else:
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

    log_debug("-> Applying configuration flags:") # Renamed log message slightly

    # --- Add Labels ---
    flags.extend(["--label", "debox.managed=true"])
    flags.extend(["--label", f"debox.app.name={config.get('app_name', 'unknown')}"])
    flags.extend(["--label", f"debox.container.name={container_name}"])
    
    # --- User Namespaces ---
    flags.append("--userns=keep-id") 

    # --- Permissions Section ---
    log_debug("   Applying permissions:")

    # Network
    net_perm = permissions.get('network', True) 
    if not net_perm:
        flags.append("--network=none")
        log_debug("     - Network: Disabled")
    else:
        flags.append("--network=default")
        log_debug("     - Network: Enabled (connected to 'default' CNI bridge)")

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
        log_debug(f"     - System D-Bus: Enabled (read-only, socket: {actual_sys_dbus_socket})")
    else:
        log_debug(f"     - System D-Bus: Disabled {'(socket not found at expected locations)' if sys_dbus_perm else ''}")

    # Bluetooth (Relies on System D-Bus)
    bt_perm = permissions.get('bluetooth', False)
    if bt_perm:
        if sys_dbus_perm and actual_sys_dbus_socket: log_debug("     - Bluetooth: Enabled (via System D-Bus)")
        else: log_debug("     - Bluetooth: Disabled (requires System D-Bus)");
    else: log_debug("     - Bluetooth: Disabled")

    # Printers (Relies on CUPS socket)
    printer_perm = permissions.get('printers', False)
    cups_socket = Path("/run/cups/cups.sock")
    if printer_perm:
        if cups_socket.is_socket(): flags.extend(["-v", f"{cups_socket}:{cups_socket}:rw"]); log_debug("     - Printers: Enabled (via CUPS socket)")
        else: log_debug("     - Printers: Disabled (CUPS socket not found)")
    else: log_debug("     - Printers: Disabled")

    # Webcam
    webcam_perm = permissions.get('webcam', False)
    if webcam_perm:
        video_devices = list(Path("/dev").glob("video*"))
        if video_devices:
            for dev in video_devices: flags.extend(["--device", str(dev)])
            log_debug(f"     - Webcam: Enabled ({len(video_devices)} device(s))")
        else: log_debug("     - Webcam: Disabled (no devices found)")
    else: log_debug("     - Webcam: Disabled")

    # Microphone (Relies on Sound/Desktop Integration)
    mic_perm = permissions.get('microphone', False)
    if mic_perm: log_debug("     - Microphone: Enabled (via session bus)") # Assume enabled if requested & integration on
    else: log_debug("     - Microphone: Disabled")

    # Explicit Devices
    explicit_devices = permissions.get('devices', [])
    if explicit_devices:
        log_debug("     - Explicit Devices:")
        for device in explicit_devices:
             # Add check if device exists
             if Path(device).exists(): flags.extend(["--device", device]); log_debug(f"       - Added: {device}")
             else: log_debug(f"       - Warning: Device '{device}' not found. Skipping.")
    else: log_debug("     - Explicit Devices: None")

    # --- Integration Section (GPU/Sound flags depend on this) ---
    log_debug("   Applying integration settings:")
    desktop_integration_enabled = integration_cfg.get('desktop_integration', True)
    if desktop_integration_enabled:
        log_debug("     - Desktop Integration: Enabled")
        xdg_runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
        if not xdg_runtime_dir: log_debug("       Warning: XDG_RUNTIME_DIR not set.")
        else: flags.extend(["-v", f"{xdg_runtime_dir}:{xdg_runtime_dir}:rw"]) # Mount session dir

        # Pass essential env vars
        essential_env_vars = ["DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR",
                              "DBUS_SESSION_BUS_ADDRESS", "PULSE_SERVER", "XDG_SESSION_TYPE"]
        for var in essential_env_vars:
             if os.environ.get(var): flags.extend(["-e", var])

        xauth_path = os.environ.get("XAUTHORITY", os.path.expanduser("~/.Xauthority"))
        
        if Path(xauth_path).is_file():
            # Montujemy go w bezpiecznym miejscu w kontenerze (np. /tmp/.Xauthority)
            # i ustawiamy zmienną środowiskową, aby aplikacja wiedziała, gdzie go szukać.
            container_xauth_path = "/tmp/.Xauthority"
            flags.extend(["-v", f"{xauth_path}:{container_xauth_path}:ro"])
            flags.extend(["-e", f"XAUTHORITY={container_xauth_path}"])
            log_debug(f"     - X11 Auth: Mounted {xauth_path} -> {container_xauth_path}")
        else:
            log_debug(f"     - X11 Auth: File not found at {xauth_path}. X11 apps might fail.")
        
        # Apply GPU based on permission AND integration flag
        gpu_perm = permissions.get('gpu', True) # Default true if integration enabled
        if gpu_perm:
             if Path("/dev/dri").exists(): flags.append("--device=/dev/dri"); log_debug("     - GPU: Enabled")
             else: log_debug("     - GPU: Disabled (host device /dev/dri not found)")
        else: log_debug("     - GPU: Disabled")

        # Apply Sound based on permission AND integration flag
        sound_perm = permissions.get('sound', True) # Default true if integration enabled
        if sound_perm: log_debug("     - Sound: Enabled (via session bus)")
        else: log_debug("     - Sound: Disabled")
    else:
        log_debug("     - Desktop Integration: Disabled")
        log_debug("     - GPU: Disabled") # Force disable if integration is off
        log_debug("     - Sound: Disabled") # Force disable if integration is off

    # --- Storage Section ---
    log_debug("   Applying storage settings:")
    # Isolated Home (Always added)
    home_dir = config_utils.get_app_home_dir(container_name)
    flags.extend(["-v", f"{home_dir}:{os.path.expanduser('~')}:Z"])
    log_debug(f"     - Isolated Home: {home_dir} -> ~")
    # Additional Volumes
    volumes = storage_cfg.get('volumes', [])
    if volumes:
        for volume in volumes:
            try:
                parts = volume.split(':')
                
                if len(parts) == 2:
                    host_path, container_path = parts
                    options = "Z" 
                elif len(parts) == 3:
                    host_path, container_path, options = parts
                else:
                    raise ValueError("Expected 2 or 3 parts separated by ':'")

                expanded_host_path = os.path.expanduser(host_path)
                
                # Złóż flagę z powrotem
                volume_flag = f"{expanded_host_path}:{container_path}:{options}"
                flags.extend(["-v", volume_flag])
                
                log_debug(f"     - Additional: {volume_flag}")
            except ValueError:
                log_warning(f"     - Invalid volume format: '{volume}'. Skipping.")
    else:
        log_debug("     - Additional Volumes: None")

    log_debug("-> Finished applying configuration flags.")
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
    
    log_debug("--- Building Container Image ---")
    
    # Get host details
    host_user = getpass.getuser()
    host_uid = os.getuid()
    host_locale = "C.UTF-8"
    try:
        loc = locale.getlocale(locale.LC_CTYPE)
        host_locale = f"{loc[0]}.{loc[1]}" if loc[0] and loc[1] else "C.UTF-8"
    except Exception as e:
        log_warning(f"Failed to detect host locale ({e}), defaulting.")
    log_debug(f"-> Using host details: User={host_user}, UID={host_uid}, Locale={host_locale}")

    # Generate Containerfile content
    containerfile = _generate_containerfile(config, host_user, host_uid, host_locale)
    (app_config_dir / "Containerfile").write_text(containerfile) # Save for reference
    log_debug("-> Generated Containerfile.")

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
        log_debug(f"-> Successfully built image '{image_tag}'")
        return image_tag
    except Exception as e:
        log_error(f"Building image failed: {e}")
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
    log_debug(f"--- Creating Container Instance: {container_name} ---")
    
    # Generate flags based on config
    podman_flags = _generate_podman_flags(config)
    
    # Execute container creation
    try:
        podman_utils.create_container(container_name, image_tag, podman_flags)
        log_debug(f"-> Successfully created container '{container_name}'")
    except Exception as e:
        log_error(f"Creating container failed: {e}")
        raise # Re-raise the exception

def remove_container_instance(container_name: str):
    """
    Stops (if running) and removes the container instance.
    Ignores errors if the container doesn't exist.
    """
    log_debug(f"-> Stopping container '{container_name}' (if running)...")
    try:
        podman_utils.run_command(["podman", "stop", "--ignore", "--time=2", container_name])
    except Exception as e:
        log_warning(f"  Failed to stop container (might be already stopped): {e}")
        
    log_debug(f"-> Removing container '{container_name}'...")
    try:
        podman_utils.run_command(["podman", "rm", "--ignore", container_name])
        log_debug(f"--> Container '{container_name}' removed.")
    except Exception as e:
        log_warning(f"  Failed to remove container (might be already removed): {e}")

def remove_container_image(container_name: str):
    """
    Removes the container image associated with the container name.
    Ignores errors if the image doesn't exist.
    """
    image_tag = f"localhost/{container_name}:latest"
    log_debug(f"-> Removing image '{image_tag}'...")
    try:
        podman_utils.run_command(["podman", "rmi", "--ignore", image_tag])
        log_debug(f"--> Image '{image_tag}' removed.")
    except Exception as e:
        log_warning(f"  Failed to remove image (might be already removed or in use): {e}")

def restore_container_from_registry(config: dict) -> bool:
    """
    Checks if the container exists. If not, attempts to restore it
    by checking for a local image, or pulling from the registry.
    Returns True if restoration was performed, False if not needed or failed.
    """
    container_name = config['container_name']
    image_tag = f"localhost/{container_name}:latest"

    status = podman_utils.get_container_status(container_name)
    if "run" in status.lower() or "exited" in status.lower() or "created" in status.lower():
        return False

    print(f"-> Container '{container_name}' missing. Initiating restore sequence...")

    if not podman_utils.local_image_exists(image_tag):
        print(f"-> Local image '{image_tag}' missing. Attempting pull from registry...")
        try:
            # To używa run_step wewnątrz registry_utils (jeśli tam jest) lub musimy to obsłużyć
            # registry_utils.pull_image_from_registry rzuca wyjątek w razie błędu
            registry_utils.pull_image_from_registry(container_name)
            print("-> Image restored from registry.")
        except Exception as e:
            print(f"❌ Error: Failed to pull image from registry: {e}")
            raise # Przekaż błąd wyżej
    else:
        print("-> Local image found.")

    print("-> Recreating container instance...")
    create_container_instance(config, image_tag)
    
    return True