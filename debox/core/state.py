# debox/core/state.py
"""
Global state holder for the application.

This module holds a singleton 'state' object that can be imported
by any other module to check global settings, like verbosity.
"""

class AppState:
    """A simple class to hold the application's global state."""
    def __init__(self):
        self.verbose = False

# Create a single, global instance that all modules will share.
state = AppState()