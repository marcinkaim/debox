# debox/commands/install_cmd.py

from pathlib import Path
import shutil
import getpass
import os
import locale
from debox.core import config as config_utils
from debox.core import podman_utils
from debox.core import desktop_integration

def install_app(config_path: Path):
    """
    Orchestrates the entire application installation process,
    checking first if the application container already exists,
    and setting the container locale to match the host.
    """
    # 1. Load and validate the configuration
    try:
        config = config_utils.load_config(config_path)
        container_name = config['container_name']
    except Exception as e:
        print(f"Error loading configuration: {e}")
        return # Exit if config is invalid

    # --- Check if container already exists ---
    print(f"-> Checking status for container '{container_name}'...")
    existing_status = podman_utils.get_container_status(container_name)

    if existing_status != "Not Found" and "error" not in existing_status.lower():
        print(f"❌ Error: Container '{container_name}' already exists (Status: {existing_status}).")
        print("   If you want to reinstall, please remove the existing application first using:")
        print(f"   debox remove \"{config.get('app_name', container_name)}\"")
        return # Exit gracefully
    elif "error" in existing_status.lower():
         print(f"Warning: Could not reliably determine status for {container_name}. Proceeding with caution.")
    else:
         print(f"-> Container '{container_name}' not found. Proceeding with installation...")
    
    # 2. Prepare debox directories for the app (this is safe to re-run)
    app_config_dir = config_utils.get_app_config_dir(container_name)
    try:
        shutil.copy(config_path, app_config_dir / "config.yml")
        print(f"-> Copied config to {app_config_dir}")
    except Exception as e:
        print(f"Error copying configuration: {e}")
        return # Exit if copying fails
    
    # 3. Generate Containerfile and build the image
    try:
        # --- Get host user details AND locale ---
        host_user = getpass.getuser()
        host_uid = os.getuid()
        host_locale = "C.UTF-8" # Default
        try:
            loc = locale.getlocale(locale.LC_CTYPE)
            host_locale = f"{loc[0]}.{loc[1]}" if loc[0] and loc[1] else "C.UTF-8"
        except Exception as e:
             print(f"Warning: Error detecting host locale ({e}), defaulting.")
        print(f"-> Using host locale: {host_locale}")

        # --- Pass the full config to _generate_containerfile ---
        # It reads image section, no changes needed inside it yet.
        containerfile = _generate_containerfile(config, host_user, host_uid, host_locale)
        (app_config_dir / "Containerfile").write_text(containerfile)
        print("-> Generated Containerfile.")

        # --- Copy keep_alive script (if still using it) ---
        current_dir = Path(__file__).parent
        keep_alive_script_src = current_dir.parent / "core" / "keep_alive.py"
        if keep_alive_script_src.is_file():
            keep_alive_script_dest = app_config_dir / "keep_alive.py"
            shutil.copy(keep_alive_script_src, keep_alive_script_dest)
            print(f"-> Copied keep_alive.py to build context: {keep_alive_script_dest}")
        else:
             print("Warning: keep_alive.py not found, CMD might be missing.")
        
        image_tag = f"localhost/{container_name}:latest"
        build_args = {"HOST_USER": host_user, "HOST_UID": str(host_uid), "HOST_LOCALE": host_locale}
        image_label = {"debox.managed": "true"}

        podman_utils.build_image(
            containerfile,
            image_tag,
            context_dir=app_config_dir,
            build_args=build_args,
            labels=image_label
        )
        print(f"-> Successfully built image '{image_tag}'")
    except Exception as e:
        print(f"Error building image: {e}")
        return
        
    # 4. Generate podman flags and create the container
    try:
        # --- Pass the full config to _generate_podman_flags ---
        podman_flags = _generate_podman_flags(config)
        podman_utils.create_container(container_name, image_tag, podman_flags)
        print(f"-> Successfully created container '{container_name}'")
    except Exception as e:
         print(f"Error creating container: {e}")
         return

    # 5. Call desktop integration function
    try:
        # --- Pass the full config to desktop_integration ---
        desktop_integration.add_desktop_integration(config)
    except Exception as e:
         print(f"Error during desktop integration: {e}")
         return
    
    print("\n✅ Installation complete!")

def _generate_containerfile(config: dict, host_user: str, host_uid: int, host_locale: str) -> str:
    """
    Generates the content of the Containerfile based on the YAML config.
    """
    lines = [f"FROM {config['image']['base']}"]
    
    # --- Add arguments for user creation ---
    lines.append(f"ARG HOST_USER={host_user}")
    lines.append(f"ARG HOST_UID={host_uid}")
    lines.append(f"ARG HOST_LOCALE={host_locale}") # Define locale arg

    # Add environment variable to prevent interactive prompts during package installation
    lines.append("ENV DEBIAN_FRONTEND=noninteractive")
    
    # Pre-install dependencies for adding repositories
    lines.append("RUN apt-get update && apt-get install -y wget gpg sudo locales python3 && apt-get clean")

    # Locale generation
    lines.append(f"RUN sed -i -e 's/# $HOST_LOCALE UTF-8/$HOST_LOCALE UTF-8/' /etc/locale.gen")
    lines.append(f"RUN dpkg-reconfigure --frontend=noninteractive locales")
    lines.append(f"ENV LANG=$HOST_LOCALE")
    
    # Handle repositories
    if config.get('image', {}).get('repositories'):
        for repo in config['image']['repositories']:
            key_path = repo.get('key_path') # Use .get()
            key_url = repo.get('key_url')
            repo_string = repo.get('repo_string')
            if not (key_path and key_url and repo_string):
                 print(f"Warning: Skipping invalid repository entry: {repo}")
                 continue
            lines.append(f"RUN mkdir -p $(dirname {key_path})")
            lines.append(f"RUN wget -qO- {key_url} | gpg --dearmor > {key_path}")
            lines.append(f"RUN echo \"{repo_string}\" > /etc/apt/sources.list.d/{config['container_name']}.list")

    # Handle package installation
    packages_to_install = config.get('image', {}).get('packages', [])
    if packages_to_install:
        packages_str = " ".join(packages_to_install)
        lines.append(f"RUN apt-get update && apt-get install -y {packages_str} && apt-get clean")

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
    Generates the list of flags for the 'podman create' command,
    including full desktop integration flags.
    """
    flags = []

    permissions = config.get('permissions', {})
    storage_cfg = config.get('storage', {})
    runtime_cfg = config.get('runtime', {})
    integration_cfg = config.get('integration', {})
    container_name = config['container_name']

    print("-> Applying configuration:") # Changed log message

    # --- ADD LABEL TO CONTAINER ---
    flags.extend(["--label", "debox.managed=true"])
    flags.extend(["--label", f"debox.app.name={config.get('app_name', 'unknown')}"]) # Optional extra info
    flags.extend(["--label", f"debox.container.name={container_name}"]) # Optional extra info

    # --- User Namespaces ---
    flags.append("--userns=keep-id")

    # --- Permissions Section ---
    print("   Applying permissions:")

    # Network
    net_perm = permissions.get('network', True)
    if not net_perm: flags.append("--network=none"); print("     - Network: Disabled")
    else: print("     - Network: Enabled (default)")

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
        print(f"     - System D-Bus: Enabled (read-only, socket: {actual_sys_dbus_socket})")
    else:
        print(f"     - System D-Bus: Disabled {'(socket not found at expected locations)' if sys_dbus_perm else ''}")

    # Bluetooth (Relies on System D-Bus)
    bt_perm = permissions.get('bluetooth', False)
    if bt_perm:
        if sys_dbus_perm and actual_sys_dbus_socket: print("     - Bluetooth: Enabled (via System D-Bus)")
        else: print("     - Bluetooth: Disabled (requires System D-Bus)");
    else: print("     - Bluetooth: Disabled")

    # Printers (Relies on CUPS socket)
    printer_perm = permissions.get('printers', False)
    cups_socket = Path("/run/cups/cups.sock")
    if printer_perm:
        if cups_socket.is_socket(): flags.extend(["-v", f"{cups_socket}:{cups_socket}:rw"]); print("     - Printers: Enabled (via CUPS socket)")
        else: print("     - Printers: Disabled (CUPS socket not found)")
    else: print("     - Printers: Disabled")

    # Webcam
    webcam_perm = permissions.get('webcam', False)
    if webcam_perm:
        video_devices = list(Path("/dev").glob("video*"))
        if video_devices:
            for dev in video_devices: flags.extend(["--device", str(dev)])
            print(f"     - Webcam: Enabled ({len(video_devices)} device(s))")
        else: print("     - Webcam: Disabled (no devices found)")
    else: print("     - Webcam: Disabled")

    # Microphone (Relies on Sound/Desktop Integration)
    mic_perm = permissions.get('microphone', False)
    if mic_perm: print("     - Microphone: Enabled (via session bus)") # Assume enabled if requested & integration on
    else: print("     - Microphone: Disabled")

    # Explicit Devices
    explicit_devices = permissions.get('devices', [])
    if explicit_devices:
        print("     - Explicit Devices:")
        for device in explicit_devices:
             # Add check if device exists
             if Path(device).exists(): flags.extend(["--device", device]); print(f"       - Added: {device}")
             else: print(f"       - Warning: Device '{device}' not found. Skipping.")
    else: print("     - Explicit Devices: None")

    # --- Integration Section (GPU/Sound flags depend on this) ---
    print("   Applying integration settings:")
    desktop_integration_enabled = integration_cfg.get('desktop_integration', True)
    if desktop_integration_enabled:
        print("     - Desktop Integration: Enabled")
        xdg_runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
        if not xdg_runtime_dir: print("       Warning: XDG_RUNTIME_DIR not set.")
        else: flags.extend(["-v", f"{xdg_runtime_dir}:{xdg_runtime_dir}:rw"]) # Mount session dir

        # Pass essential env vars
        essential_env_vars = ["DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR",
                              "DBUS_SESSION_BUS_ADDRESS", "PULSE_SERVER", "XDG_SESSION_TYPE"]
        for var in essential_env_vars:
             if os.environ.get(var): flags.extend(["-e", var])

        # Apply GPU based on permission AND integration flag
        gpu_perm = permissions.get('gpu', True) # Default true if integration enabled
        if gpu_perm:
             if Path("/dev/dri").exists(): flags.append("--device=/dev/dri"); print("     - GPU: Enabled")
             else: print("     - GPU: Disabled (host device /dev/dri not found)")
        else: print("     - GPU: Disabled")

        # Apply Sound based on permission AND integration flag
        sound_perm = permissions.get('sound', True) # Default true if integration enabled
        if sound_perm: print("     - Sound: Enabled (via session bus)")
        else: print("     - Sound: Disabled")
    else:
         print("     - Desktop Integration: Disabled")
         print("     - GPU: Disabled") # Force disable if integration is off
         print("     - Sound: Disabled") # Force disable if integration is off

    # --- Storage Section ---
    print("   Applying storage settings:")
    # Isolated Home (Always added)
    home_dir = config_utils.get_app_home_dir(container_name)
    flags.extend(["-v", f"{home_dir}:{os.path.expanduser('~')}:Z"])
    print(f"     - Isolated Home: {home_dir} -> ~")
    # Additional Volumes
    volumes = storage_cfg.get('volumes', [])
    if volumes:
        for volume in volumes:
            try:
                host_path, container_path = volume.split(':')
                expanded_host_path = os.path.expanduser(host_path)
                # Add check if host path exists? Maybe optional.
                flags.extend(["-v", f"{expanded_host_path}:{container_path}:Z"])
                print(f"     - Additional: {expanded_host_path} -> {container_path}")
            except ValueError:
                print(f"     - Warning: Invalid volume format: '{volume}'. Skipping.")
    else:
         print("     - Additional Volumes: None")

    print("-> Finished applying configuration flags.")
    return flags