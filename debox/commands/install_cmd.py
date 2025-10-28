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
    
    # --- Get host user details AND locale ---
    host_user = getpass.getuser()
    host_uid = os.getuid()
    try:
        # Get the host's default locale (e.g., 'pl_PL.UTF-8')
        host_locale = locale.getlocale(locale.LC_CTYPE)[0] + '.' + locale.getlocale(locale.LC_CTYPE)[1]
        if not host_locale or '.' not in host_locale: # Fallback if detection fails
             print("Warning: Could not detect host locale, defaulting to C.UTF-8")
             host_locale = "C.UTF-8"
    except Exception as e:
         print(f"Warning: Error detecting host locale ({e}), defaulting to C.UTF-8")
         host_locale = "C.UTF-8"

    print(f"-> Using host locale: {host_locale}")
    
    # --- Make sure keep_alive.py exists ---
    # Determine path relative to the install_cmd.py file
    current_dir = Path(__file__).parent
    keep_alive_script_src = current_dir.parent / "core" / "keep_alive.py"
    if not keep_alive_script_src.is_file():
         print("Error: keep_alive.py not found!")
         return # Or raise an exception

    # --- Copy keep_alive.py to the app's config dir ---
    # So podman build can access it via context
    keep_alive_script_dest = app_config_dir / "keep_alive.py"
    shutil.copy(keep_alive_script_src, keep_alive_script_dest)
    print(f"-> Copied keep_alive.py to build context: {keep_alive_script_dest}")
    
    # 3. Generate Containerfile and build the image
    try:
        containerfile = _generate_containerfile(config, host_user, host_uid, host_locale)
        (app_config_dir / "Containerfile").write_text(containerfile)
        print("-> Generated Containerfile.")
        
        image_tag = f"localhost/{container_name}:latest"
        build_args = {
            "HOST_USER": host_user,
            "HOST_UID": str(host_uid),
            "HOST_LOCALE": host_locale,
        }

        # --- ADD LABEL TO IMAGE ---
        image_label = {"debox.managed": "true"}

        podman_utils.build_image(
            containerfile, 
            image_tag, 
            context_dir=app_config_dir, 
            build_args=build_args,
            labels=image_label
        )
        print(f"-> Successfully built and labeled image '{image_tag}'")
    except Exception as e:
        print(f"Error building image: {e}")
        # Attempt cleanup? Maybe just exit for now.
        return
        
    # 4. Generate podman flags and create the container
    try:
        podman_flags = _generate_podman_flags(config)
        podman_utils.create_container(container_name, image_tag, podman_flags)
        print(f"-> Successfully created container '{container_name}'")
    except Exception as e:
         print(f"Error creating container: {e}")
         # Attempt cleanup? Maybe just exit for now.
         return

    # 5. Export the .desktop file for desktop integration
    if config.get('runtime', {}).get('desktop_integration', True):
        try:
            desktop_integration.add_desktop_integration(config)
            # Success message is now inside _export_desktop_file if it runs
        except Exception as e:
             print(f"Error during desktop integration export: {e}")
             return
    else:
        print("-> Desktop integration disabled. Skipping desktop file and icon export.")

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

    # --- Locale generation and configuration ---
    # Configure locales package - uncomment the desired locale in the config file
    lines.append(f"RUN sed -i -e 's/# $HOST_LOCALE UTF-8/$HOST_LOCALE UTF-8/' /etc/locale.gen")
    # Generate the locale
    lines.append(f"RUN dpkg-reconfigure --frontend=noninteractive locales")
    # Set the generated locale as the default LANG environment variable
    lines.append(f"ENV LANG=$HOST_LOCALE")
    
    # Handle repositories
    if config['image'].get('repositories'):
        for repo in config['image']['repositories']:
            # Use the key_path directly from the config file
            key_path = repo['key_path']
            
            # Create the parent directory for the key if it doesn't exist
            lines.append(f"RUN mkdir -p $(dirname {key_path})")
            
            # Download the key to the correct path
            lines.append(f"RUN wget -qO- {repo['key_url']} | gpg --dearmor > {key_path}")
            
            # Add the repository source file
            lines.append(f"RUN echo \"{repo['repo_string']}\" > /etc/apt/sources.list.d/{config['container_name']}.list")

    # Handle package installation
    packages_str = " ".join(config['image']['packages'])
    # We run 'apt-get update' again to pick up the new repository list
    lines.append(f"RUN apt-get update && apt-get install -y {packages_str} && apt-get clean")
    
    # --- Create the user at the end of the build ---
    # This creates a user with the same name and UID as the host user.
    # -m creates the home directory. -s sets the default shell.
    lines.append(f"RUN useradd -m -s /bin/bash -u $HOST_UID $HOST_USER")
    # Optional: Add the user to the sudo group for convenience inside the container
    lines.append(f"RUN usermod -aG sudo $HOST_USER")
    lines.append(f'RUN echo "$HOST_USER ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers')

    # --- Copy and set execution permissions for the script ---
    lines.append("COPY keep_alive.py /usr/local/bin/keep_alive.py")
    lines.append("RUN chmod +x /usr/local/bin/keep_alive.py")
    
    # --- Set the script as the default command ---
    # This will be overridden by create_container, but good practice
    lines.append('CMD ["/usr/local/bin/keep_alive.py"]')
    
    return "\n".join(lines)

def _generate_podman_flags(config: dict) -> list[str]:
    """
    Generates the list of flags for the 'podman create' command,
    including full desktop integration flags.
    """
    flags = []

    container_name = config['container_name'] # Get container name

    # --- ADD LABEL TO CONTAINER ---
    flags.extend(["--label", "debox.managed=true"])
    flags.extend(["--label", f"debox.app.name={config.get('app_name', 'unknown')}"]) # Optional extra info
    flags.extend(["--label", f"debox.container.name={container_name}"]) # Optional extra info

    # --- Add the crucial flag to keep the host user ID ---
    # This disables user namespace mapping and allows the container user
    # to have the same UID as the host user, which is essential for
    # accessing host resources like Wayland and D-Bus sockets.
    flags.append("--userns=keep-id")

    print("-> Applying permissions:") # Log start
    permissions = config.get('permissions', {})

    # --- Network ---
    net_perm = permissions.get('network', True)
    if not net_perm:
        flags.append("--network=none")
        print("   - Network: Disabled")
    else:
        # Default Podman network ('full' implies default)
        print("   - Network: Enabled (default bridge)")

    # --- Desktop Integration Base (Required for most GUI permissions) ---
    desktop_integration_enabled = config.get('runtime', {}).get('desktop_integration', True)
    if desktop_integration_enabled:
        print("   - Desktop Integration: Enabled")
        xdg_runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
        if not xdg_runtime_dir:
            print("     Warning: XDG_RUNTIME_DIR is not set. GUI apps may fail.")
        
        essential_env_vars = ["DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", 
                              "DBUS_SESSION_BUS_ADDRESS", "PULSE_SERVER", "XDG_SESSION_TYPE"]
        for var in essential_env_vars:
             if os.environ.get(var): flags.extend(["-e", var])
        
        # Mount user session directory (contains Wayland, session D-Bus, Pipewire/Pulse sockets)
        if xdg_runtime_dir:
            flags.extend(["-v", f"{xdg_runtime_dir}:{xdg_runtime_dir}:rw"]) 
    else:
         print("   - Desktop Integration: Disabled")

    # --- GPU Acceleration ---
    # Default to True if desktop integration is enabled
    gpu_perm = permissions.get('gpu', desktop_integration_enabled) 
    if desktop_integration_enabled and gpu_perm: # Check boolean True
        if Path("/dev/dri").exists():
             flags.append("--device=/dev/dri")
             print("   - GPU (/dev/dri): Enabled")
        else:
             print("     Warning: /dev/dri not found on host, cannot enable GPU.")
    else:
        print("   - GPU (/dev/dri): Disabled")

    # --- Sound ---
    # Default to True if desktop integration is enabled
    sound_perm = permissions.get('sound', desktop_integration_enabled) 
    if desktop_integration_enabled and sound_perm: # Check boolean True
        print("   - Sound: Enabled (via session bus)")
    else:
        print("   - Sound: Disabled")

    # --- System D-Bus ---
    # Default to True
    sys_dbus_perm = permissions.get('system_dbus', True) 
    sys_dbus_socket = Path("/var/run/dbus/system_bus_socket")
    if sys_dbus_perm and sys_dbus_socket.is_socket(): # Check boolean True
        flags.extend(["-v", f"{sys_dbus_socket}:{sys_dbus_socket}:ro"])
        print("   - System D-Bus: Enabled (read-only)")
    else:
        print(f"   - System D-Bus: Disabled {'(socket not found)' if sys_dbus_perm else ''}")

    # --- Bluetooth ---
    # Default to False
    bt_perm = permissions.get('bluetooth', False) 
    if bt_perm: # Check boolean True
        if sys_dbus_perm and sys_dbus_socket.is_socket():
            print("   - Bluetooth: Enabled (via System D-Bus)")
        else:
            print("     Warning: Bluetooth requires 'system_dbus: true'.")
            print("   - Bluetooth: Disabled (System D-Bus missing)")
    else:
        print("   - Bluetooth: Disabled")

    # --- Webcam ---
    # Default to False
    webcam_perm = permissions.get('webcam', False) 
    if webcam_perm: # Check boolean True
        video_devices = list(Path("/dev").glob("video*"))
        if video_devices:
            for dev in video_devices: flags.extend(["--device", str(dev)])
            print(f"   - Webcam: Enabled (found {len(video_devices)} device(s))")
        else:
            print("     Warning: Webcam requested, but no /dev/video* found.")
            print("   - Webcam: Disabled (device not found)")
    else:
        print("   - Webcam: Disabled")

    # --- Microphone ---
    # Default to False
    mic_perm = permissions.get('microphone', False) 
    if mic_perm: # Check boolean True
        if desktop_integration_enabled and os.environ.get("XDG_RUNTIME_DIR"):
            print("   - Microphone: Enabled (via session bus)")
        else:
             print("     Warning: Microphone access requires desktop integration.")
             print("   - Microphone: Disabled")
    else:
        print("   - Microphone: Disabled")

    # --- Printers ---
    # Default to False
    printer_perm = permissions.get('printers', False) 
    cups_socket = Path("/run/cups/cups.sock")
    if printer_perm: # Check boolean True
        if cups_socket.is_socket():
             flags.extend(["-v", f"{cups_socket}:{cups_socket}:rw"]) 
             print("   - Printers: Enabled (via CUPS socket)")
        else:
             print("     Warning: Printer access requested, but CUPS socket not found.")
             print("   - Printers: Disabled (socket not found)")
    else:
         print("   - Printers: Disabled")

    # --- Explicit Devices ---
    explicit_devices = permissions.get('devices', [])
    if explicit_devices:
        print("   - Explicit Devices:")
        for device in explicit_devices:
            if Path(device).exists():
                 flags.extend(["--device", device])
                 print(f"     - Added: {device}")
            else:
                 print(f"     - Warning: Device '{device}' not found on host. Skipping.")
    else:
         print("   - Explicit Devices: None")
         
    # --- Volumes (Remain the same) ---
    print("   - Volumes:")
    # Isolated Home
    home_dir = config_utils.get_app_home_dir(container_name)
    flags.extend(["-v", f"{home_dir}:{os.path.expanduser('~')}:Z"])
    print(f"     - Isolated Home: {home_dir} -> ~")
    # Additional Volumes
    for volume in config.get('runtime', {}).get('volumes', []):
        try:
            host_path, container_path = volume.split(':')
            expanded_host_path = os.path.expanduser(host_path)
            flags.extend(["-v", f"{expanded_host_path}:{container_path}:Z"])
            print(f"     - Additional: {expanded_host_path} -> {container_path}")
        except ValueError:
            print(f"     - Warning: Invalid volume format: '{volume}'. Skipping.")

    print("-> Finished applying permissions.")
    return flags