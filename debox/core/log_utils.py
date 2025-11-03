# debox/core/log_utils.py
"""
Central logging utility for debox.
Reads the global state to determine verbosity.
"""

from debox.core import state

def log_verbose(message: str):
    """
    Prints a message to the console only if
    the global verbose flag (state.state.verbose) is set to True.
    """
    if state.state.verbose:
        print(message)