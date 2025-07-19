"""
Utilities for redirecting stdout to prevent MCP protocol corruption.

MCP (Model Context Protocol) uses stdout for JSON-RPC communication.
Any non-JSON output to stdout will corrupt the protocol and cause client errors.
This module provides context managers to safely redirect stdout during operations
that might produce unwanted output.
"""

import sys
import io
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)


@contextmanager
def redirect_stdout_to_stderr():
    """
    Context manager that redirects stdout to stderr temporarily.
    
    This is critical for MCP servers where stdout is reserved for JSON-RPC.
    Any warnings, print statements, or other output must go to stderr.
    
    Usage:
        with redirect_stdout_to_stderr():
            # Code that might print to stdout
            model.solve()
    """
    old_stdout = sys.stdout
    try:
        sys.stdout = sys.stderr
        yield
    finally:
        sys.stdout = old_stdout


@contextmanager
def capture_stdout():
    """
    Context manager that captures stdout to a string buffer.
    
    Returns the captured output as a string.
    
    Usage:
        with capture_stdout() as output:
            # Code that might print to stdout
            model.solve()
        captured_text = output.getvalue()
    """
    old_stdout = sys.stdout
    stdout_buffer = io.StringIO()
    try:
        sys.stdout = stdout_buffer
        yield stdout_buffer
    finally:
        sys.stdout = old_stdout
        

@contextmanager
def suppress_stdout():
    """
    Context manager that completely suppresses stdout.
    
    Usage:
        with suppress_stdout():
            # Code whose stdout output should be discarded
            model.initialize()
    """
    old_stdout = sys.stdout
    try:
        sys.stdout = io.StringIO()
        yield
    finally:
        sys.stdout = old_stdout