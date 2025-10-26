# debox/commands/install_cmd.py

from pathlib import Path
import shlex
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
    if config.get('runtime', {}).get('desktop_integration', True):
        print("-> Desktop integration enabled. Exporting desktop file and icons...")
        try:
            _export_desktop_file(config) 
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
            "XDG_SESSION_TYPE", # Explicitly tell it's Wayland
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
    Temporarily starts the container, finds ALL .desktop files,
    extracts ALL associated icons with prefixed names,
    modifies Exec lines by prepending 'debox run <container> -- ',
    sets prefixed icon names in ALL sections, saves modified .desktop files
    with unique names, and updates host caches.
    """
    container_name = config['container_name']
    desktop_files_processed = 0
    icons_were_copied = False
    
    # --- Get skip_categories from config ---
    # Read the list from the YAML, default to an empty list if not specified
    skip_categories_set = set(config.get('runtime', {}).get('skip_categories', []))
    if skip_categories_set:
        print(f"-> Will skip exporting .desktop files with categories: {list(skip_categories_set)}")
    else:
        print("-> No categories specified to skip. Will export all valid apps.")
        
    try:
        print("-> Temporarily starting container...")
        podman_utils.run_command(["podman", "start", container_name])
        print("-> Waiting for container to initialize...")
        time.sleep(2) 
        status = podman_utils.get_container_status(container_name)
        print(f"-> Container status: {status}")
        if "run" not in status.lower():
             raise RuntimeError(f"Container {container_name} failed to start properly.")

        # --- 1. Find ALL .desktop files in the container ---
        print("-> Searching for all .desktop files in container...")
        find_cmd = [
            "podman", "exec", container_name, 
            "find", "/usr/share/applications/", "/usr/local/share/applications/", 
            "-type", "f", "-name", "*.desktop" 
        ]
        process = subprocess.run(find_cmd, capture_output=True, text=True, check=False)
        found_desktop_paths = process.stdout.strip().splitlines()

        if process.returncode != 0 and not found_desktop_paths:
             print(f"Warning: 'find' command for .desktop files failed: {process.stderr}")
             return 
        if not found_desktop_paths:
             print("Warning: No .desktop files found in the container.")
             return

        print(f"-> Found {len(found_desktop_paths)} potential .desktop file(s). Processing...")

        all_icon_names_to_export = set()
        # Store tuples: (original_path, parser_obj, original_exec_map)
        # original_exec_map = {section_name: original_exec_string}
        parsed_data = [] 

        # --- 2. Loop 1: Parse files, gather icons, store original Exec ---
        for desktop_path_in_container in found_desktop_paths:
            try:
                print(f"--> Processing: {desktop_path_in_container}")
                cat_cmd = ["podman", "exec", container_name, "cat", desktop_path_in_container]
                original_content = podman_utils.run_command(cat_cmd, capture_output=True)
                
                parser = configparser.ConfigParser(interpolation=None)
                parser.optionxform = str 
                parser.read_string(original_content)

                if 'Desktop Entry' not in parser or not parser.getboolean('Desktop Entry', 'NoDisplay', fallback=False) is False:
                     if 'Desktop Entry' in parser and parser.getboolean('Desktop Entry', 'NoDisplay', fallback=False):
                          print(f"--> Skipping hidden file (NoDisplay=true): {desktop_path_in_container}")
                     else:
                          print(f"--> Skipping invalid file (no [Desktop Entry]): {desktop_path_in_container}")
                     continue

                # --- Check Categories using config ---
                categories_str = parser.get('Desktop Entry', 'Categories', fallback='')
                # Ensure categories are split correctly, handling potential multiple semicolons
                categories = set(cat.strip() for cat in categories_str.split(';') if cat.strip())
                
                # Check if any category is in the skip list from the config
                if skip_categories_set.intersection(categories): # Use the set from config
                     print(f"--> Skipping file due to category: {desktop_path_in_container} (Categories: {categories_str})")
                     continue
                
                original_exec_map = {}
                # Collect icons and original Exec commands from all sections
                for section_name in parser.sections():
                    section = parser[section_name]
                    if 'Exec' in section:
                        original_exec_map[section_name] = section['Exec'] # Store original command
                    
                    icon_in_section = section.get('Icon')
                    if icon_in_section:
                        all_icon_names_to_export.add(icon_in_section)
                
                # Only proceed if at least one Exec command was found
                if original_exec_map:
                    parsed_data.append((desktop_path_in_container, parser, original_exec_map))
                    desktop_files_processed += 1
                else:
                    print(f"--> Skipping file with no Exec command: {desktop_path_in_container}")

            except Exception as parse_e:
                print(f"--> Warning: Failed to parse or process {desktop_path_in_container}: {parse_e}")

        if not parsed_data:
             print("Error: No valid .desktop files with Exec commands could be processed.")
             return

        # Add fallback icon if none were found at all
        if not all_icon_names_to_export:
             all_icon_names_to_export.add("application-default-icon")
        
        final_icon_list = list(all_icon_names_to_export)
        print(f"-> Identified {len(final_icon_list)} unique icon name(s) to export: {final_icon_list}")

        # --- 3. Call icon export function with the full list ---
        icons_were_copied = _export_icons(container_name, final_icon_list)

        # --- 4. Loop 2: Modify Exec/Icon entries and save .desktop files ---
        print("-> Saving modified .desktop files...")
        for original_path, parser, original_exec_map in parsed_data:
            original_filename = Path(original_path).name
            
            # Modify Exec and Icon entries in all sections
            for section_name in parser.sections():
                section = parser[section_name]
                
                # --- CORE CHANGE: Prepend 'debox run' to ORIGINAL Exec ---
                if section_name in original_exec_map:
                    original_exec = original_exec_map[section_name]
                    # Prepend 'debox run <container> -- ' to the original command
                    section['Exec'] = f"debox run {container_name} -- {original_exec}"
                
                # Prefix Icon name (same logic as before)
                original_icon_name = section.get('Icon')
                if original_icon_name:
                    prefixed_icon_name = f"{container_name}_{original_icon_name}"
                    section['Icon'] = prefixed_icon_name
                elif section_name == 'Desktop Entry' and final_icon_list: # Fallback for main entry
                    section['Icon'] = f"{container_name}_{final_icon_list[0]}"

            # Modify main Name entry
            if 'Desktop Entry' in parser:
                main_section = parser['Desktop Entry']
                main_section['Name'] = f"{main_section.get('Name', original_filename)} ({container_name})"

            # Construct final path on host using prefixed filename
            final_desktop_filename = f"{container_name}_{original_filename}"
            final_desktop_path = config_utils.DESKTOP_FILES_DIR / final_desktop_filename
            
            try:
                with open(final_desktop_path, 'w') as f:
                    parser.write(f, space_around_delimiters=False)
                print(f"--> Saved: {final_desktop_path}")
            except Exception as write_e:
                 print(f"--> Error writing {final_desktop_path}: {write_e}")

        # --- 5. Update caches ---
        if icons_were_copied:
             print("-> Updating icon cache...")
             try: # Add try-except for robustness
                 podman_utils.run_command(["gtk-update-icon-cache", "-f", "-t", str(Path(os.path.expanduser("~/.local/share/icons")))])
             except Exception as cache_e:
                  print(f"Warning: Failed to update icon cache: {cache_e}")
             
        print("-> Updating desktop application database...")
        podman_utils.run_command(["update-desktop-database", str(config_utils.DESKTOP_FILES_DIR)])

        print(f"-> Successfully processed {desktop_files_processed} desktop file(s).")

    except Exception as e:
         print(f"Error during desktop file export process: {e}")
    finally:
        # Stop the temporary container
        print("-> Stopping temporary container...")
        podman_utils.run_command(["podman", "stop", "--time=2", container_name])

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