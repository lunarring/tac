"""
Trusty Agents package for TAC.

This package contains all the trusty agents that can be used to verify
the correctness of a protoblock implementation.
"""

import importlib
import pkgutil
import logging
import traceback

logger = logging.getLogger(__name__)

def load_all_agents():
    """Dynamically import all trusty agent modules to ensure they're registered."""
    logger.info("Loading all trusty agents...")
    
    # Get the path to the trusty_agents package
    import tac.trusty_agents as agents_pkg
    
    # Define the order of modules to load to avoid circular imports
    ordered_modules = ['base', 'registry', 'pytest', 'plausibility', 'pexpect_agent', 'threejs_unit_test', 'threejs_vision', 'vision']
    
    # First load the ordered modules
    for name in ordered_modules:
        try:
            # Import the module to trigger registration
            importlib.import_module(f"tac.trusty_agents.{name}")
            logger.info(f"Loaded trusty agent module: {name}")
        except ImportError as e:
            # This is an expected error - module might not exist
            logger.debug(f"Skipping optional trusty agent module '{name}': {e}")
        except Exception as e:
            # Print the full traceback for better debugging
            logger.error(f"Error loading trusty agent module {name}: {e}")
            logger.debug(traceback.format_exc())
    
    # Then load any remaining modules
    for _, name, _ in pkgutil.iter_modules(agents_pkg.__path__):
        # Skip modules that have already been loaded
        if name in ordered_modules or name == '__init__':
            continue
        try:
            # Import the module to trigger registration
            importlib.import_module(f"tac.trusty_agents.{name}")
            logger.info(f"Loaded trusty agent module: {name}")
        except ImportError as e:
            # This is an expected error - module might not exist or have missing dependencies
            logger.debug(f"Skipping optional trusty agent module '{name}': {e}")
        except Exception as e:
            # Print the full traceback for better debugging
            logger.error(f"Error loading trusty agent module {name}: {e}")
            logger.debug(traceback.format_exc())

# Load all agents when the package is imported
try:
    load_all_agents()
except Exception as e:
    logger.error(f"Error loading trusty agents: {e}")
