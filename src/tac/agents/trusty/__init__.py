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
    import tac.agents.trusty as agents_pkg
    
    # Define modules that need to be loaded first due to dependencies
    priority_modules = ['base', 'registry']
    
    # First load the priority modules that others might depend on
    for name in priority_modules:
        try:
            importlib.import_module(f"tac.agents.trusty.{name}")
            logger.info(f"Loaded priority trusty agent module: {name}")
        except ImportError as e:
            logger.debug(f"Skipping priority trusty agent module '{name}': {e}")
        except Exception as e:
            logger.error(f"Error loading priority trusty agent module {name}: {e}")
            logger.debug(traceback.format_exc())
    
    # Then load all remaining modules
    for _, name, _ in pkgutil.iter_modules(agents_pkg.__path__):
        # Skip modules that have already been loaded or should be ignored
        if name in priority_modules or name == '__init__':
            continue
        try:
            importlib.import_module(f"tac.agents.trusty.{name}")
            logger.info(f"Loaded trusty agent module: {name}")
        except ImportError as e:
            logger.debug(f"Skipping optional trusty agent module '{name}': {e}")
        except Exception as e:
            logger.error(f"Error loading trusty agent module {name}: {e}")
            logger.debug(traceback.format_exc())

# Load all agents when the package is imported
try:
    load_all_agents()
except Exception as e:
    logger.error(f"Error loading trusty agents: {e}")

from tac.agents.trusty.base import TrustyAgent, ComparativeTrustyAgent
from tac.agents.trusty.registry import TrustyAgentRegistry
from tac.agents.trusty.results import TrustyAgentResult
from tac.agents.trusty.ui import ConsoleResultRenderer, HTMLResultRenderer

# Import all agents to ensure they register
import tac.agents.trusty.pytest
import tac.agents.trusty.threejs_vision
import tac.agents.trusty.threejs_vision_before_after
import tac.agents.trusty.threejs_vision_reference
import tac.agents.trusty.pexpect_agent
import tac.agents.trusty.plausibility

# Import performance agent (optional)
try:
    import tac.agents.trusty.performance
except ImportError:
    pass  # Performance agent is optional

# Export publicly useful classes
__all__ = [
    'TrustyAgent', 
    'ComparativeTrustyAgent', 
    'TrustyAgentRegistry',
    'TrustyAgentResult',
    'ConsoleResultRenderer',
    'HTMLResultRenderer'
]
