# debox/core/log_utils.py
"""
Central logging utility for debox.
Reads the global state to determine verbosity.
"""

import contextlib
import sys
from rich.console import Console
from debox.core import state

console = Console(highlight=False)

def log_verbose(message: str):
    """
    Prints a message to the console only if
    the global verbose flag (state.state.verbose) is set to True.
    """
    if state.state.verbose:
        console.print(message)

@contextlib.contextmanager
def run_step(spinner_message: str, success_message: str, error_message: str):
    """
    A context manager that wraps a long-running code block.
    
    - In silent mode: Shows a spinner.
    - In verbose mode: Shows nothing (logs are printed by the code block).
    - On success: Prints the success_message.
    - On failure: Prints the error_message, formatted, and exits.
    """
    try:
        if state.state.verbose:
            yield None
        else:
            with console.status(spinner_message) as status:
                yield status
        
        if success_message:
            console.print(success_message)
    
    except SystemExit as e:
        raise e
    except Exception as e:
        console.print(f"❌ {error_message}", style="bold red") 
        sys.exit(1)