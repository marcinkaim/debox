# debox/commands/install_cmd.py

from pathlib import Path
import os
import shutil
import configparser
import subprocess
from debox.core import config as config_utils
from debox.core import podman_utils
import getpass
import os

def install_app(config_path: Path):
    """
    Orchestrates the entire application installation process.
    """
    # 1. Load and validate the configuration
    config = config_utils.load_config(config_path)
    container_name = config['container_name']
    
    # 2. Prepare debox directories for the app
    app_config_dir = config_utils.get_app_config_dir(container_name)
    shutil.copy(config_path, app_config_dir / "config.yml")
    print(f"-> Copied config to {app_config_dir}")

    # --- Get host user details ---
    host_user = getpass.getuser()
    host_uid = os.getuid()

    # 3. Generate Containerfile and build the image
    containerfile = _generate_containerfile(config, host_user, host_uid)
    (app_config_dir / "Containerfile").write_text(containerfile)
    print("-> Generated Containerfile.")
    
    image_tag = f"localhost/{container_name}:latest"
    # Pass user details as build arguments to podman
    build_args = {
        "HOST_USER": host_user,
        "HOST_UID": str(host_uid),
    }
    podman_utils.build_image(containerfile, image_tag, build_args)
    print(f"-> Successfully built image '{image_tag}'")
    
    # 4. Generate podman flags and create the container
    podman_flags = _generate_podman_flags(config)
    podman_utils.create_container(container_name, image_tag, podman_flags)
    print(f"-> Successfully created container '{container_name}'")
    
    # 5. Export the .desktop file for desktop integration
    _export_desktop_file(config)
    print(f"-> Successfully exported desktop file for '{config['app_name']}'")
    print("\n✅ Installation complete!")

def _generate_containerfile(config: dict, host_user: str, host_uid: int) -> str:
    """
    Generates the content of the Containerfile based on the YAML config.
    """
    lines = [f"FROM {config['image']['base']}"]
    
    # --- Add arguments for user creation ---
    lines.append(f"ARG HOST_USER={host_user}")
    lines.append(f"ARG HOST_UID={host_uid}")

    # Add environment variable to prevent interactive prompts during package installation
    lines.append("ENV DEBIAN_FRONTEND=noninteractive")
    
    # Pre-install dependencies for adding repositories
    lines.append("RUN apt-get update && apt-get install -y wget gpg sudo")
    
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

    return "\n".join(lines)

def _generate_podman_flags(config: dict) -> list[str]:
    """
    Generates the list of flags for the 'podman create' command,
    including full desktop integration flags.
    """
    flags = []
    
    # --- Add the crucial flag to keep the host user ID ---
    # This disables user namespace mapping and allows the container user
    # to have the same UID as the host user, which is essential for
    # accessing host resources like Wayland and D-Bus sockets.
    flags.append("--userns=keep-id")
    
    # Handle desktop integration
    if config.get('runtime', {}).get('desktop_integration', True):
        xdg_runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
        if not xdg_runtime_dir:
            print("Warning: XDG_RUNTIME_DIR is not set. GUI applications may not work.")
        
        # Define a list of essential environment variables to pass from host to container
        essential_env_vars = [
            "DISPLAY",
            "WAYLAND_DISPLAY",
            "XDG_RUNTIME_DIR", # Crucial for Wayland, D-Bus, and Pipewire sockets
            "DBUS_SESSION_BUS_ADDRESS", # Crucial for D-Bus communication
            "PULSE_SERVER", # For audio (PulseAudio/Pipewire)
        ]
        
        for var in essential_env_vars:
            if os.environ.get(var):
                flags.extend(["-e", var])

        # Mount essential sockets for GUI operation
        flags.extend([
            "--device", "/dev/dri", # For GPU acceleration
            # Mount the system D-Bus socket for system-wide services communication.
            # It's read-only as the app only needs to talk to it, not modify it.
            "-v", "/var/run/dbus/system_bus_socket:/var/run/dbus/system_bus_socket:ro"])
        
        if xdg_runtime_dir:
            # Mount the entire runtime directory, which contains sockets for
            # Wayland, D-Bus, Pipewire, etc.
            flags.extend(["-v", f"{xdg_runtime_dir}:{xdg_runtime_dir}:rw"])

    # Handle isolated home directory
    home_dir = config_utils.get_app_home_dir(config['container_name'])
    flags.extend(["-v", f"{home_dir}:{os.path.expanduser('~')}:Z"])
    
    # Handle additional volumes
    for volume in config.get('runtime', {}).get('volumes', []):
        host_path, container_path = volume.split(':')
        expanded_host_path = os.path.expanduser(host_path)
        flags.extend(["-v", f"{expanded_host_path}:{container_path}:Z"])

    return flags

def _export_desktop_file(config: dict):
    """
    Temporarily starts the container to find the original .desktop file,
    intelligently modifies its Exec lines, copies ALL associated icons 
    preserving their directory structure, and integrates with the host desktop.
    """
    container_name = config['container_name']
    base_binary = config['export']['binary']
    
    try:
        # --- Start the container temporarily ---
        print("-> Temporarily starting container to extract files...")
        podman_utils.run_command(["podman", "start", container_name])

        original_desktop_content = ""
        try:
            # 1. Find and read the original .desktop file from the container
            find_cmd = ["podman", "exec", container_name, "find", "/usr/share/applications/", "-name", f"{base_binary}.desktop"]
            desktop_path_in_container = podman_utils.run_command(find_cmd, capture_output=True).strip()

            if not desktop_path_in_container:
                raise FileNotFoundError("Original .desktop file not found in container.")

            cat_cmd = ["podman", "exec", container_name, "cat", desktop_path_in_container]
            original_desktop_content = podman_utils.run_command(cat_cmd, capture_output=True)
            print(f"-> Found original .desktop file at: {desktop_path_in_container}")

        except Exception as e:
            print(f"-> Warning: Could not find or read original .desktop file. Will generate a basic one. Error: {e}")
            # If we can't find the original, we fall back to the old method of generating a basic file
            original_desktop_content = f"""[Desktop Entry]
Name={config['app_name']}
Exec={base_binary}
Icon=application-default-icon
Type=Application
"""

        # 2. Parse the .desktop content to extract information
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str
        parser.read_string(original_desktop_content)

        # 3. Determine the icon name with priority
        icon_name = config.get('export', {}).get('icon') or parser.get('Desktop Entry', 'Icon', fallback=base_binary)
        print(f"-> Using icon name: '{icon_name}' (will keep this name in the final .desktop)")

        # 4. Extract the icon file from the container
        icons_copied_count = 0
        try:
            # Search only in standard icon directories
            find_icon_cmd = ["podman", "exec", container_name, "find", "/usr/share/icons/", "/usr/share/pixmaps/", "-name", f"{icon_name}.*"]
            # Again, use check=False and capture output
            process_icons = subprocess.run(find_icon_cmd, capture_output=True, text=True, check=False)
            found_icons = process_icons.stdout.strip().splitlines()

            if process_icons.returncode != 0 and not found_icons:
                raise FileNotFoundError(f"find command for icons failed: {process_icons.stderr}")
            if not found_icons:
                 raise FileNotFoundError(f"Icon files for '{icon_name}' not found.")

            print(f"-> Found {len(found_icons)} icon file(s) for '{icon_name}'. Copying...")
            
            for icon_path_in_container in found_icons:
                icon_path = Path(icon_path_in_container)
                
                # Determine the relative path and corresponding host path
                if icon_path.is_relative_to("/usr/share/icons"):
                    relative_path = icon_path.relative_to("/usr/share/icons")
                    host_dest_path = Path(os.path.expanduser("~/.local/share/icons")) / relative_path
                elif icon_path.is_relative_to("/usr/share/pixmaps"):
                    relative_path = icon_path.relative_to("/usr/share/pixmaps")
                    host_dest_path = Path(os.path.expanduser("~/.local/share/pixmaps")) / relative_path
                else:
                    print(f"-> Warning: Skipping icon with unknown base path: {icon_path}")
                    continue
                
                # Create parent directories on the host
                host_dest_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Copy the icon file
                cp_cmd = ["podman", "cp", f"{container_name}:{icon_path_in_container}", str(host_dest_path)]
                podman_utils.run_command(cp_cmd)
                icons_copied_count += 1
            
            if icons_copied_count > 0:
                 print(f"-> Successfully copied {icons_copied_count} icon file(s).")
            else:
                 print("-> Warning: No icons were successfully copied.")

        except Exception as e:
            print(f"-> Warning: Failed during icon extraction. Error: {e}")


        # 5. Iterate over ALL sections in the .desktop file
        for section_name in parser.sections():
            section = parser[section_name]
            
            # 5a. Modify the 'Exec' line if it exists
            if 'Exec' in section:
                original_exec = section['Exec']
                exec_parts = original_exec.split()
                # Replace only the main command, keeping all arguments (%F, --new-window, etc.)
                exec_parts[0] = f"debox run {container_name}"
                section['Exec'] = " ".join(exec_parts)
            
        # 6. Modify the main entry's Name to distinguish it
        if 'Desktop Entry' in parser:
            main_section = parser['Desktop Entry']
            main_section['Name'] = f"{main_section.get('Name', config['app_name'])} (Debox)"

        # 7. Write the final .desktop file
        final_desktop_path = config_utils.DESKTOP_FILES_DIR / f"{container_name}.desktop"
        with open(final_desktop_path, 'w') as f:
            parser.write(f, space_around_delimiters=False)
        print(f"-> Created modified desktop file at {final_desktop_path}")
        
        # 8. Update icon cache only if icons were copied
        if icons_copied_count > 0:
             print("-> Updating icon cache...")
             # Force update for user's icon themes
             podman_utils.run_command(["gtk-update-icon-cache", "-f", "-t", str(Path(os.path.expanduser("~/.local/share/icons")))])

        # 9. Update the desktop database
        print("-> Updating desktop application database...")
        podman_utils.run_command(["update-desktop-database", str(config_utils.DESKTOP_FILES_DIR)])

    finally:
        # --- Always stop the container afterward ---
        print("-> Stopping temporary container...")
        podman_utils.run_command(["podman", "stop", "--time", "2", container_name])
