"""
Centralized logging configuration for MCP server.

This module ensures all logging goes to stderr to avoid corrupting
the MCP JSON-RPC protocol on stdout.
"""

import logging
import sys


def configure_mcp_logging():
    """
    Configure all loggers to use stderr only.
    
    This prevents any logging output from going to stdout which would
    corrupt the MCP JSON-RPC protocol.
    """
    # Get the root logger
    root_logger = logging.getLogger()
    
    # Remove ALL existing handlers from root logger
    root_logger.handlers = []
    
    # Create a single stderr handler
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(
        logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    )
    
    # Add handler to root logger
    root_logger.addHandler(stderr_handler)
    root_logger.setLevel(logging.INFO)
    
    # Configure specific loggers to not propagate
    loggers_to_configure = [
        'utils.optimize_ro',
        'utils.simulate_ro',
        'utils.ro_model_builder',
        'utils.ro_solver',
        'utils.ro_initialization',
        'utils.ro_results_extractor',
        'utils.mcas_builder',
        'idaes',
        'pyomo',
        'watertap'
    ]
    
    for logger_name in loggers_to_configure:
        logger = logging.getLogger(logger_name)
        logger.propagate = True  # Do propagate to root which only has stderr handler
        
    # Suppress verbose loggers
    logging.getLogger('idaes.core.util.scaling').setLevel(logging.ERROR)
    logging.getLogger('pyomo.repn.plugins.nl_writer').setLevel(logging.ERROR)
    logging.getLogger('idaes.init').setLevel(logging.ERROR)
    
    
def get_configured_logger(name):
    """
    Get a logger that's properly configured for MCP.
    
    Args:
        name: Logger name (usually __name__)
        
    Returns:
        logging.Logger: Configured logger
    """
    logger = logging.getLogger(name)
    # Ensure it propagates to root logger which only outputs to stderr
    logger.propagate = True
    # Don't add any handlers - use root's stderr handler
    logger.handlers = []
    return logger