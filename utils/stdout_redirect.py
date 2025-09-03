"""
Utilities for redirecting stdout to prevent MCP protocol corruption.

MCP (Model Context Protocol) uses stdout for JSON-RPC communication.
Any non-JSON output to stdout will corrupt the protocol and cause client errors.
This module provides context managers to safely redirect/suppress stdout during
operations that might produce unwanted output.
"""

import sys
import io
import os
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)


@contextmanager
def redirect_stdout_to_stderr():
    """
    Lightweight redirection of Python-level stdout to stderr.

    Note: This only affects Python's sys.stdout. It does NOT affect OS-level
    file descriptor 1. C-extensions or native solvers that write to stdout
    will still write to FD 1 and can corrupt the MCP protocol.
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
    Capture Python-level stdout to a string buffer.

    This does not capture OS-level (FD 1) writes from native extensions.
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
    Suppress Python-level stdout only (sys.stdout).

    OS-level writes to FD 1 are NOT suppressed.
    """
    old_stdout = sys.stdout
    try:
        sys.stdout = io.StringIO()
        yield
    finally:
        sys.stdout = old_stdout


@contextmanager
def suppress_stdout_fd():
    """
    Suppress ALL stdout, including OS-level FD 1, for the duration of the block.

    This protects the MCP STDIO transport from being corrupted or deadlocked by
    native libraries (e.g., solvers) that write directly to stdout. It redirects
    FD 1 to os.devnull and also rebinds Python's sys.stdout accordingly.

    WARNING: This changes process-wide FD 1 temporarily. Use in a narrow scope
    where no MCP JSON-RPC messages are emitted, and restore immediately after.
    """
    # Flush any pending output
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass

    old_stdout = sys.stdout
    try:
        # Duplicate current stdout FD so we can restore later
        saved_stdout_fd = os.dup(old_stdout.fileno())

        # Open devnull for writing and redirect FD 1 there
        devnull = open(os.devnull, 'w')
        os.dup2(devnull.fileno(), old_stdout.fileno())

        # Point Python-level stdout at devnull as well
        sys.stdout = devnull

        yield
    finally:
        # Flush and restore Python-level stdout first
        try:
            sys.stdout.flush()
        except Exception:
            pass

        # Restore FD 1 from the saved duplicate
        try:
            os.dup2(saved_stdout_fd, old_stdout.fileno())
        finally:
            try:
                os.close(saved_stdout_fd)
            except Exception:
                pass

        # Restore Python-level stdout object
        sys.stdout = old_stdout
        # Close devnull if still open
        try:
            devnull.close()
        except Exception:
            pass
