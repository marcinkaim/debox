# debox/commands/install_cmd.py

from pathlib import Path
import shutil
import configparser
import subprocess
import time
from debox.core import config as config_utils
from debox.core import podman_utils
import getpass
import os
import locale

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

        # Pass the app_config_dir as the context directory
        podman_utils.build_image(containerfile, image_tag, context_dir=app_config_dir, build_args=build_args)
        print(f"-> Successfully built image '{image_tag}'")
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
    try:
        _export_desktop_file(config)
        # The success message is now inside _export_desktop_file
    except Exception as e:
         print(f"Error exporting desktop file: {e}")
         # Attempt cleanup? Maybe just exit for now.
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
    Temporarily starts the container, waits for it to be running,
    finds/parses the .desktop file, determines icon names, calls _export_icons,
    modifies Exec lines, sets the prefixed icon name, and integrates.
    """
    container_name = config['container_name']
    binary = config['export']['binary']
    
    try:
        # --- Start the container temporarily ---
        print("-> Temporarily starting container to extract files...")
        podman_utils.run_command(["podman", "start", container_name])

        # # Wait a couple of seconds for the container to fully start
        # print("-> Waiting for container to initialize...")
        # time.sleep(2) # Wait for 2 seconds
        
        # # Check status (optional but good for debugging)
        # status = podman_utils.get_container_status(container_name)
        # print(f"-> Container status: {status}")
        # if "run" not in status.lower():
        #      raise RuntimeError(f"Container {container_name} failed to start properly.")
        
        # --- Find and parse the original .desktop file ---
        original_desktop_content = ""
        desktop_path_in_container = ""
        try:
            find_cmd = ["podman", "exec", container_name, "find", "/usr/share/applications/", "/usr/local/share/applications/", "-name", f"{binary}.desktop"]
            process = subprocess.run(find_cmd, capture_output=True, text=True, check=False)
            found_desktops = process.stdout.strip().splitlines()
            
            if process.returncode != 0 and not found_desktops: raise FileNotFoundError(f"find failed: {process.stderr}")
            if not found_desktops: raise FileNotFoundError("Original .desktop not found.")
            
            desktop_path_in_container = found_desktops[0]
            cat_cmd = ["podman", "exec", container_name, "cat", desktop_path_in_container]
            original_desktop_content = podman_utils.run_command(cat_cmd, capture_output=True)
            print(f"-> Found original .desktop file at: {desktop_path_in_container}")

        except Exception as e:
            print(f"-> Warning: Could not find original .desktop file. Generating basic. Error: {e}")
            original_desktop_content = f"[Desktop Entry]\nName={config['app_name']}\nExec={binary}\nIcon={binary}\nType=Application"

        # Parse the .desktop content to extract information
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str
        parser.read_string(original_desktop_content)

        # --- Determine the LIST of ALL unique icon names ---
        icon_names_to_export = set() # Use a set to automatically handle duplicates

        # Priority 1: Use the list from YAML if provided and not empty
        yaml_icons = config.get('export', {}).get('icons', [])
        if yaml_icons:
            icon_names_to_export.update(yaml_icons) # Add all icons from YAML
            print(f"-> Using icon names specified in YAML: {list(icon_names_to_export)}")
        else:
            # Priority 2: Scan ALL sections of the .desktop file for 'Icon=' keys
            print("-> Scanning .desktop file for icon names...")
            for section_name in parser.sections():
                icon_in_section = parser.get(section_name, 'Icon', fallback=None)
                if icon_in_section:
                    icon_names_to_export.add(icon_in_section) # Add unique icon names

            if icon_names_to_export:
                print(f"-> Found icon names in .desktop file: {list(icon_names_to_export)}")
            else:
                 # Priority 3: Fallback to a standard default icon name
                 print(f"-> No icons found in YAML or .desktop. Falling back to default.")
                 icon_names_to_export.add("application-default-icon") # Use a generic fallback

        # Convert set back to list for the export function
        final_icon_list = list(icon_names_to_export)

        # --- Call the dedicated icon export function with the full list ---
        icons_were_copied = _export_icons(container_name, final_icon_list)

        # --- Modify ALL relevant sections in the parser ---
        for section_name in parser.sections():
            section = parser[section_name]
            
            # 5a. Modify the 'Exec' line if it exists
            if 'Exec' in section:
                original_exec = section['Exec']
                exec_parts = original_exec.split()
                # Replace only the main command, keeping all arguments (%F, --new-window, etc.)
                exec_parts[0] = f"debox run {container_name}"
                section['Exec'] = " ".join(exec_parts)

            # --- Prefix the Icon name IN THIS SPECIFIC SECTION ---
            # Use the icon name originally found in this section
            original_icon_name_in_section = parser.get(section_name, 'Icon', fallback=None)
            if original_icon_name_in_section:
                 # Create the prefixed name for *this specific icon*
                 prefixed_icon_name = f"{container_name}_{original_icon_name_in_section}"
                 section['Icon'] = prefixed_icon_name
            elif section_name == 'Desktop Entry' and final_icon_list:
                 # If main entry had no icon, use the first one from our list (prefixed)
                 section['Icon'] = f"{container_name}_{final_icon_list[0]}"

        # Modify the main entry's Name
        if 'Desktop Entry' in parser:
            main_section = parser['Desktop Entry']
            main_section['Name'] = f"{main_section.get('Name', config['app_name'])} ({container_name})"

        # --- Write the final .desktop file ---
        final_desktop_path = config_utils.DESKTOP_FILES_DIR / f"{container_name}.desktop"
        with open(final_desktop_path, 'w') as f:
            parser.write(f, space_around_delimiters=False)
        print(f"-> Created modified desktop file at {final_desktop_path}")
        
        # --- Update icon cache and desktop database ---
        if icons_were_copied:
             print("-> Updating icon cache...")
             try: # Add try-except for robustness
                 podman_utils.run_command(["gtk-update-icon-cache", "-f", "-t", str(Path(os.path.expanduser("~/.local/share/icons")))])
             except Exception as cache_e:
                  print(f"Warning: Failed to update icon cache: {cache_e}")

        # 9. Update the desktop database
        print("-> Updating desktop application database...")
        podman_utils.run_command(["update-desktop-database", str(config_utils.DESKTOP_FILES_DIR)])
        
        print(f"-> Successfully exported desktop file for '{config['app_name']}'")

    finally:
        # --- Always stop the container afterward ---
        print("-> Stopping temporary container...")
        podman_utils.run_command(["podman", "stop", "--time", "2", container_name])

def _export_icons(container_name: str, icon_names: list[str]) -> bool:
    """
    Finds icon files inside the container for a list of base names,
    copies them to the corresponding user directories on the host,
    prefixing the filename with the container name.

    Args:
        container_name: The name of the container (e.g., 'debox-firefox').
        icon_names: A list of base icon names to search for (e.g., ['firefox-esr']).

    Returns:
        True if at least one icon was successfully copied, False otherwise.
    """
    icons_copied_count = 0
    print(f"-> Starting icon export for names: {icon_names}")

    for icon_name in icon_names:
        if not icon_name: # Skip empty names
            continue
        print(f"--> Searching for icons matching '{icon_name}.*'...")
        try:
            # Search only in standard icon directories
            find_icon_cmd = ["podman", "exec", container_name, "find", "/usr/share/icons/", "/usr/share/pixmaps/", "-name", f"{icon_name}.*"]
            process_icons = subprocess.run(find_icon_cmd, capture_output=True, text=True, check=False)
            found_icons = process_icons.stdout.strip().splitlines()

            if process_icons.returncode != 0 and not found_icons:
                print(f"--> Warning: 'find' command failed for icons named '{icon_name}': {process_icons.stderr}")
                continue # Try next icon name
            if not found_icons:
                 print(f"--> No icon files found for '{icon_name}'.")
                 continue # Try next icon name

            print(f"--> Found {len(found_icons)} icon file(s) for '{icon_name}'. Copying with prefix...")
            
            for icon_path_in_container in found_icons:
                try:
                    icon_path_cont = Path(icon_path_in_container)
                    icon_extension = icon_path_cont.suffix.lower()
                    
                    # --- Determine destination directory ---
                    if icon_path_cont.is_relative_to("/usr/share/icons"):
                        relative_path = icon_path_cont.relative_to("/usr/share/icons")
                        host_dest_dir = Path(os.path.expanduser("~/.local/share/icons")) / relative_path.parent
                    elif icon_path_cont.is_relative_to("/usr/share/pixmaps"):
                        # For pixmaps, place directly in user's pixmaps, no subdirs needed from relative_path
                        host_dest_dir = Path(os.path.expanduser("~/.local/share/pixmaps"))
                    else:
                        print(f"--> Warning: Skipping icon with unknown base path: {icon_path_cont}")
                        continue
                    
                    host_dest_dir.mkdir(parents=True, exist_ok=True)
                    
                    # --- Create the new prefixed filename ---
                    # e.g., debox-firefox_firefox-esr.png
                    new_icon_filename = f"{container_name}_{icon_name}{icon_extension}"
                    icon_path_on_host = host_dest_dir / new_icon_filename
                    
                    # --- Copy the icon ---
                    cp_cmd = ["podman", "cp", f"{container_name}:{icon_path_in_container}", str(icon_path_on_host)]
                    podman_utils.run_command(cp_cmd)
                    print(f"    Copied: {icon_path_in_container} -> {icon_path_on_host}")
                    icons_copied_count += 1
                except Exception as copy_e:
                     print(f"--> Error copying icon {icon_path_in_container}: {copy_e}")

        except Exception as find_e:
            print(f"--> Error finding icons for '{icon_name}': {find_e}")

    if icons_copied_count > 0:
         print(f"-> Successfully copied {icons_copied_count} total icon file(s).")
         return True
    else:
         print("-> Warning: No icons were successfully copied.")
         return False