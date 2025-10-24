#!/usr/bin/env python3
# debox/core/keep_alive.py

import signal
import time
import sys

# Flag to control the main loop
running = True

def handle_sigterm(signum, frame):
    """Signal handler for SIGTERM and SIGINT."""
    global running
    print("Received termination signal. Exiting gracefully...")
    running = False

# Register the signal handler for SIGTERM (sent by 'podman stop')
# and SIGINT (sent by Ctrl+C if attached)
signal.signal(signal.SIGTERM, handle_sigterm)
signal.signal(signal.SIGINT, handle_sigterm)

print("Keep-alive script started. Waiting for termination signal...")

# Main loop that runs until a signal is received
while running:
    # Sleep for a short interval to avoid busy-waiting and consuming CPU
    try:
        time.sleep(1) 
    except InterruptedError:
        # Catch interruption if signal arrives during sleep
        running = False 

print("Keep-alive script finished.")
sys.exit(0) # Ensure a clean exit code