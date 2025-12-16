# debox/core/gpg_utils.py

import os
import shutil
import subprocess
from pathlib import Path
from debox.core.log_utils import log_debug, log_info, log_error, log_warning
from debox.core import config_utils

def get_gpg_context_dir(container_name: str) -> Path:
    """Returns the path to the isolated GPG home directory for a specific container."""
    return config_utils.DEBOX_SECURITY_DIR / container_name / "gnupg"

def setup_gpg_context(container_name: str, config: dict):
    """
    Sets up a dedicated GNUPGHOME for the container.
    Exports the specified key from the host and imports it into the isolated context.
    """
    security_cfg = config.get('security', {})
    gpg_key_id = security_cfg.get('gpg_key_id')

    # If no key is defined, clean up any existing context and return
    if not gpg_key_id:
        remove_gpg_context(container_name)
        return

    log_info(f"--- Setting up isolated GPG context for key: {gpg_key_id} ---")
    
    context_dir = get_gpg_context_dir(container_name)
    
    # Always start fresh to ensure the key is up-to-date with the host
    if context_dir.exists():
        shutil.rmtree(context_dir)
    
    context_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(context_dir, 0o700) # GPG requires strict permissions

    try:
        # 1. Export Public Key
        pub_cmd = ["gpg", "--export", gpg_key_id]
        proc_pub = subprocess.run(pub_cmd, capture_output=True, check=True)
        
        # 2. Export Secret Key
        sec_cmd = ["gpg", "--export-secret-keys", gpg_key_id]
        proc_sec = subprocess.run(sec_cmd, capture_output=True, check=True)

        # 3. Import to Isolated Context
        # We assume gpg 2.x which handles agent automatically, but we need to point via GNUPGHOME
        env = os.environ.copy()
        env['GNUPGHOME'] = str(context_dir)

        # Import Public
        p1 = subprocess.Popen(["gpg", "--import"], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env)
        p1.communicate(input=proc_pub.stdout)
        
        # Import Secret
        p2 = subprocess.Popen(["gpg", "--import"], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env)
        out, err = p2.communicate(input=proc_sec.stdout)

        if p2.returncode != 0:
            raise Exception(f"Failed to import secret key: {err.decode()}")

        # 4. Configure gpg-agent inside context for loopback pinentry
        # This is critical for containers without GUI access to host's pinentry
        agent_conf = context_dir / "gpg-agent.conf"
        with open(agent_conf, 'w') as f:
            f.write("allow-loopback-pinentry\n")
            # Optional: Extend cache time for convenience
            f.write("default-cache-ttl 34560000\n") 
            f.write("max-cache-ttl 34560000\n")

        log_debug(f"-> GPG context created at {context_dir}")
        log_info(f"-> Key {gpg_key_id} imported successfully into isolation.")

    except subprocess.CalledProcessError as e:
        log_error(f"Failed to export key from host (check if ID {gpg_key_id} is correct): {e}", exit_program=True)
    except Exception as e:
        log_error(f"GPG setup failed: {e}", exit_program=True)

def remove_gpg_context(container_name: str):
    """Removes the isolated GPG directory."""
    context_dir = config_utils.DEBOX_SECURITY_DIR / container_name
    if context_dir.exists():
        log_debug(f"-> Removing security context: {context_dir}")
        try:
            shutil.rmtree(context_dir)
        except Exception as e:
            log_warning(f"Failed to remove GPG context: {e}")