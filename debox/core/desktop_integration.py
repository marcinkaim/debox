# debox/core/desktop_integration.py

"""
Handles exporting .desktop files, icons, and creating command aliases
for applications installed within debox containers.
"""

import configparser
import glob
from pathlib import Path
import os
import subprocess
import time
import shlex

# Import necessary functions/constants from other core modules
from . import podman_utils
from . import config as config_utils # Use 'as' to avoid naming conflict

# --- Main Public Function for Installation ---
def add_desktop_integration(config: dict):
    """
    Public function to handle the entire desktop integration process during install.
    Finds .desktop files, exports icons, modifies files, creates aliases, updates caches.
    """
    container_name = config['container_name']
    
    integration_cfg = config.get('integration', {}) 
    alias_map = integration_cfg.get('aliases', {})
    skip_categories_set = set(integration_cfg.get('skip_categories', []))
    desktop_integration_enabled = integration_cfg.get('desktop_integration', True) # Check flag
    
    desktop_files_processed = 0
    icons_were_copied = False
    unique_base_commands = set()

    print("--- Starting Desktop Integration ---")

    if not desktop_integration_enabled:
        print("-> Desktop integration explicitly disabled in config. Skipping.")
        return # Skip the whole process if disabled

    # --- Get skip_categories from config ---
    # Read the list from the YAML, default to an empty list if not specified
    if skip_categories_set:
        print(f"-> Will skip exporting .desktop files with categories: {list(skip_categories_set)}")
    else:
        print("-> No categories specified to skip. Will export all valid apps.")
        
    try:
        print("-> Temporarily starting container for integration...")
        podman_utils.run_command(["podman", "start", container_name])
        print("-> Waiting for container to initialize...")
        time.sleep(2) 
        status = podman_utils.get_container_status(container_name)
        print(f"-> Container status: {status}")
        if "run" not in status.lower():
             raise RuntimeError(f"Container {container_name} failed to start properly.")

        # --- 1. Find ALL .desktop files in the container ---
        print("-> Searching for .desktop files in container...")
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
        parsed_data = [] # Stores tuples: (original_path, parser_obj)

        # --- 2. Loop 1: Parse files, gather icons & base commands ---
        print("-> Processing .desktop files...")
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
                
                # Collect icons and find base commands from all sections
                has_exec = False
                for section_name in parser.sections():
                    section = parser[section_name]
                    if 'Exec' in section:
                        has_exec = True
                        # --- Extract base command and add to set ---
                        original_exec = section['Exec']
                        try:
                            original_base_command = shlex.split(original_exec)[0]
                            unique_base_commands.add(original_base_command) 
                        except IndexError:
                            pass # Ignore malformed Exec lines
                    
                    icon_in_section = section.get('Icon')
                    if icon_in_section:
                        all_icon_names_to_export.add(icon_in_section)
                
                # Only store parser if it had an Exec command
                if has_exec:
                    parsed_data.append((desktop_path_in_container, parser))
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
        print("-> Saving integrated .desktop files...")
        for original_path, parser in parsed_data: # Removed original_exec_map from tuple
            original_filename = Path(original_path).name
            
            # Modify Exec and Icon entries in all sections
            for section_name in parser.sections():
                section = parser[section_name]
                
                # --- Modify 'Exec' line to use the ALIAS ---
                if 'Exec' in section:
                    original_exec = section['Exec']
                    try:
                        # Split original command to separate command from args
                        exec_parts_orig = shlex.split(original_exec)
                        if not exec_parts_orig: continue # Skip empty Exec lines

                        original_base_command = exec_parts_orig[0]
                        original_args = exec_parts_orig[1:] # Keep original args like %F, %u

                        # Determine the alias name for this command
                        command_name_only = Path(original_base_command).name 
                        alias_name = alias_map.get(command_name_only, command_name_only)

                        # Construct the new Exec line using the alias + original args
                        new_exec_parts = [alias_name] + original_args
                        section['Exec'] = " ".join(shlex.quote(part) for part in new_exec_parts) # Rejoin safely

                    except Exception as e:
                         print(f"--> Warning: Could not parse/modify Exec='{original_exec}' in section [{section_name}] of {original_filename}: {e}")
                         # Keep original Exec line if modification fails
                
                # Prefix Icon name
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

        # --- Create Aliases AFTER processing all files ---
        print("-> Creating command alias scripts...")
        aliases_created_count = 0
        if not unique_base_commands:
             print("--> No executable commands found in .desktop files to create aliases for.")
        else:
             # Check PATH once before creating aliases
             local_bin_path = str(Path(os.path.expanduser("~/.local/bin")))
             current_path = os.environ.get("PATH", "")
             if local_bin_path not in current_path.split(os.pathsep):
                 print("--- WARNING ---")
                 print(f"Directory '{local_bin_path}' is not in your PATH.") # ... (rest of warning)
                 print("---------------")

             for base_command in unique_base_commands:
                 # Get just the command name if it's a path (e.g., /usr/bin/libreoffice -> libreoffice)
                 command_name_only = Path(base_command).name 
                 # Determine the alias name using the map or the command name itself
                 alias_name = alias_map.get(command_name_only, command_name_only)
                 # Call the helper function with the BASE command
                 _create_alias_script(alias_name, container_name, base_command)
                 aliases_created_count += 1
             print(f"-> Created/Updated {aliases_created_count} alias script(s).")
        # --- End Alias Creation ---

        # --- 5. Update caches ---
        if icons_were_copied:
             print("-> Updating host icon cache...")
             try: # Add try-except for robustness
                 podman_utils.run_command(["gtk-update-icon-cache", "-f", "-t", str(Path(os.path.expanduser("~/.local/share/icons")))])
             except Exception as cache_e:
                  print(f"Warning: Failed to update icon cache: {cache_e}")
             
        print("-> Updating host desktop application database...")
        podman_utils.run_command(["update-desktop-database", str(config_utils.DESKTOP_FILES_DIR)])

        print(f"-> Successfully integrated {desktop_files_processed} application(s).")
        print("--- Desktop Integration Complete ---")

    except Exception as e:
         print(f"Error during desktop file export process: {e}")
    finally:
        # Stop the temporary container
        print("-> Stopping temporary container used for integration...")
        podman_utils.run_command(["podman", "stop", "--time=2", container_name])

def _create_alias_script(alias_name: str, container_name: str, base_command: str):
    """
    Creates an executable shell script in ~/.local/bin to act as an alias,
    passing all command-line arguments to the original command inside the container.

    Args:
        alias_name: The name of the script file to create (e.g., 'code-devbox').
        container_name: The name of the target container (e.g., 'debox-vscode').
        base_command: The original executable command inside the container (e.g., '/usr/share/code/code').
    """
    local_bin_dir = Path(os.path.expanduser("~/.local/bin"))
    local_bin_dir.mkdir(parents=True, exist_ok=True)
    alias_path = local_bin_dir / alias_name

    # --- SCRIPT CONTENT ---
    # Calls 'debox run' with the container, '--', the original base command,
    # and forwards all arguments received by the alias script ("$@").
    script_content = f"""#!/bin/sh
# Auto-generated by debox for container '{container_name}' launching '{base_command}'

debox run {container_name} -- {base_command} "$@"
"""

    try:
        # Check if a script with this name already exists and maybe warn/skip?
        # For now, we just overwrite.
        with open(alias_path, 'w') as f:
            f.write(script_content)
        os.chmod(alias_path, 0o755) # Make it executable
    except Exception as e:
        print(f"--> Warning: Failed to create alias script {alias_path}: {e}")
        raise

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
    
# --- Main Public Function for Removal ---
def remove_desktop_integration(container_name: str, config: dict):
    """
    Public function to handle the removal of all desktop integration components:
    .desktop files, icons, and alias scripts. Updates host caches afterwards.
    """
    print(f"--- Removing Desktop Integration for {container_name} ---")
    desktop_files_removed_count = 0
    icon_removed_count = 0
    aliases_removed_count = 0
    
    # Get alias map from config (needed to find correct alias scripts)
    integration_cfg = config.get('integration', {}) if config else {}
    alias_map = integration_cfg.get('aliases', {})
    commands_found_in_desktop = set() # Store commands to find aliases later

    try:
        # --- Remove .desktop files by prefix AND collect commands ---
        desktop_prefix = f"{container_name}_*.desktop"
        desktop_pattern = str(config_utils.DESKTOP_FILES_DIR / desktop_prefix)
        print(f"-> Searching for desktop files matching: {desktop_pattern}")
        
        found_desktop_files = glob.glob(desktop_pattern)
        for desktop_path_str in found_desktop_files:
            desktop_path = Path(desktop_path_str)
            if desktop_path.is_file():
                print(f"-> Processing for alias extraction: {desktop_path}")
                try:
                    # Parse desktop file BEFORE removing to find Exec command
                    temp_parser = configparser.ConfigParser(interpolation=None)
                    temp_parser.optionxform = str
                    temp_parser.read(desktop_path) 

                    # Extract alias from Exec= line (assuming it's the first word)
                    if 'Desktop Entry' in temp_parser:
                        exec_line = temp_parser.get('Desktop Entry', 'Exec', fallback=None)
                        if exec_line:
                            try:
                                alias_name_in_exec = shlex.split(exec_line)[0] 
                                # We'll need the original command name later if logic changes,
                                # but for now, the alias name is enough if needed.
                                # Let's store the alias name itself for now.
                                commands_found_in_desktop.add(alias_name_in_exec) # Storing alias name here
                            except IndexError:
                                print(f"    Warning: Could not parse Exec line: {exec_line}")
                    
                    # Remove the .desktop file
                    print(f"-> Removing desktop file: {desktop_path}")
                    desktop_path.unlink()
                    desktop_files_removed_count += 1
                    
                except Exception as e: 
                    print(f"-> Warning: Could not process or remove desktop file {desktop_path}: {e}")

        # --- Remove icon files by prefix ---
        icon_prefix_pattern = f"{container_name}_*.*" 
        print(f"-> Searching for icon files starting with '{container_name}_'...")
        user_icon_dir = Path(os.path.expanduser("~/.local/share/icons"))
        user_pixmap_dir = Path(os.path.expanduser("~/.local/share/pixmaps"))

        # Search icons dir
        if user_icon_dir.is_dir():
            for icon_path in user_icon_dir.rglob(icon_prefix_pattern): 
                if icon_path.is_file():
                    # print(f"--> Found and removing icon: {icon_path}") # Optional: less verbose
                    try:
                        icon_path.unlink()
                        icon_removed_count += 1
                    except OSError as e:
                        print(f"-> Warning: Could not remove icon {icon_path}: {e}")
        
        # Search pixmaps dir
        if user_pixmap_dir.is_dir():
             for icon_path in user_pixmap_dir.glob(icon_prefix_pattern): 
                 if icon_path.is_file():
                     # print(f"--> Found and removing icon: {icon_path}") # Optional: less verbose
                     try:
                         icon_path.unlink()
                         icon_removed_count += 1
                     except OSError as e:
                         print(f"-> Warning: Could not remove icon {icon_path}: {e}")

        # --- Remove Alias Scripts ---
        # Note: Logic simplifies - we remove aliases found in Exec lines directly
        print("-> Removing associated alias scripts...")
        local_bin_dir = Path(os.path.expanduser("~/.local/bin"))
        
        if not commands_found_in_desktop:
             print("--> No potential aliases identified from removed .desktop files.")
        elif not local_bin_dir.is_dir():
             print(f"--> Warning: Local bin directory not found: {local_bin_dir}.")
        else:
            print(f"--> Aliases identified for potential removal: {list(commands_found_in_desktop)}")
            for alias_name in commands_found_in_desktop: # Now contains actual alias names
                alias_path = local_bin_dir / alias_name
                if alias_path.is_file():
                    # Optional safety check: verify script content
                    print(f"--> Found and removing alias script: {alias_path}")
                    try:
                        alias_path.unlink()
                        aliases_removed_count += 1
                    except OSError as e:
                        print(f"--> Warning: Could not remove alias script {alias_path}: {e}")
                #else:
                #    print(f"---> Alias script not found: {alias_path}")


        # --- Update Caches ---
        if desktop_files_removed_count > 0:
            print("-> Updating desktop application database...")
            try: 
                podman_utils.run_command(["update-desktop-database", str(config_utils.DESKTOP_FILES_DIR)])
            except Exception as db_e:
                 print(f"Warning: Failed to update desktop database: {db_e}")

        if icon_removed_count > 0:
            print(f"-> Removed {icon_removed_count} icon file(s).")
            print("-> Updating icon cache...")
            try:
                podman_utils.run_command(["gtk-update-icon-cache", "-f", "-t", str(user_icon_dir)])
            except Exception as cache_e:
                 print(f"Warning: Failed to update icon cache: {cache_e}")
        else:
            print("-> No icon files found or removed.")
            
        if aliases_removed_count > 0:
             print(f"-> Removed {aliases_removed_count} alias script(s).")

        print("--- Desktop Integration Removal Complete ---")
    except Exception as e:
        print(f"Warning: Error during desktop integration cleanup for {container_name}: {e}")