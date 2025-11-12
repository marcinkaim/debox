#!/usr/bin/env python3
# debox/core/keep_alive.py

import signal
import sys
import os
import time

def handle_sigterm(signum, frame):
    """
    Signal handler for SIGTERM (from 'podman stop') and SIGINT (Ctrl+C).
    This function is called immediately when the signal is received.
    """
    os._exit(0)

signal.signal(signal.SIGTERM, handle_sigterm)
signal.signal(signal.SIGINT, handle_sigterm)

while True:
    try:
        signal.pause()
    except InterruptedError:
        pass
    except KeyboardInterrupt:
        pass
