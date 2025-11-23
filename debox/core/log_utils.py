# debox/core/log_utils.py
"""
Central logging utility for debox.
Provides logging functions (debug, info, warning, error)
and a context manager for steps (run_step).
Log level is managed globally.
"""

import contextlib
import sys
import subprocess
from rich.console import Console

console = Console(highlight=False)

class LogLevels:
    """Defines available log levels."""
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40

CURRENT_LOG_LEVEL = LogLevels.INFO

def set_log_level(level: int):
    """Sets the global log level for the application."""
    global CURRENT_LOG_LEVEL
    CURRENT_LOG_LEVEL = level

@contextlib.contextmanager
def temp_log_level(level: int):
    """
    Context manager to temporarily set the log level.
    Used by meta-commands like 'network'.
    """
    global CURRENT_LOG_LEVEL
    original_level = CURRENT_LOG_LEVEL
    try:
        set_log_level(level)
        yield
    finally:
        set_log_level(original_level)

def log_debug(message: str):
    """Logs a verbose message (only visible with --verbose)."""
    if CURRENT_LOG_LEVEL <= LogLevels.DEBUG:
        console.print(f"{message}", style="dim")

def log_info(message: str):
    """Logs a standard informational message."""
    if CURRENT_LOG_LEVEL <= LogLevels.INFO:
        console.print(message)

def log_warning(message: str):
    """Logs a warning message."""
    if CURRENT_LOG_LEVEL <= LogLevels.WARNING:
        console.print(f"⚠️ Warning: {message}", style="yellow")

def log_error(message: str, exit_program: bool = False):
    """Logs an error message and optionally exits."""
    if CURRENT_LOG_LEVEL <= LogLevels.ERROR:
        console.print(f"❌ Error: {message}", style="bold red")
    if exit_program:
        sys.exit(1)

@contextlib.contextmanager
def run_step(spinner_message: str, success_message: str, error_message: str, fatal: bool = True):
    """
    Context manager for long-running steps.
    - Shows spinner if log level is INFO.
    - Is silent if log level is DEBUG (verbose) or WARNING/ERROR.
    - Prints success/error.
    """
    try:
        if CURRENT_LOG_LEVEL == LogLevels.INFO:
            with console.status(f"[bold green]{spinner_message}") as status:
                yield status
        else:
            log_debug(f"Starting step: {spinner_message}")
            yield None
        
        log_info(success_message)
    
    except SystemExit as e:
        raise e
    except subprocess.CalledProcessError as e:
        log_error(f"{error_message}.", exit_program=fatal)
    except Exception as e:
        log_error(f"{error_message}: {e}", exit_program=fatal)