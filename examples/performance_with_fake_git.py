#!/usr/bin/env python3
"""
Example script demonstrating performance optimization with PerformanceTestingAgent.

This script shows how to optimize a function's performance using a temporary copy of the codebase
instead of modifying the actual codebase directly.
"""

import os
import sys
import logging
from pathlib import Path

# Add the src directory to the Python path
src_dir = Path(__file__).resolve().parent.parent / "src"
sys.path.append(str(src_dir))

from tac.trusty_agents.performance import PerformanceTestingAgent
from tac.core.config import load_config

# Import our example functions
from example_functions import example_function, fibonacci, find_duplicates, is_prime, sort_list

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("performance_example")

def main():
    """Run the performance optimization example."""
    
    # Load the TAC configuration
    config_path = os.environ.get("TAC_CONFIG", "config.yaml")
    config = load_config(config_path)
    
    # Function to optimize - choose one from example_functions.py
    function_name = "fibonacci"  # This recursive implementation is very inefficient
    
    # Create the performance testing agent
    logger.info(f"Creating PerformanceTestingAgent for function '{function_name}'")
    try:
        agent = PerformanceTestingAgent(
            function_name=function_name,
            config=config
        )
    except ValueError as e:
        logger.error(f"Error creating agent: {e}")
        logger.error("Make sure the function exists in your codebase.")
        return 1
    
    try:
        # Run the optimization
        logger.info("Starting optimization")
        success = agent.optimize(nmb_runs=3)  # Try 3 optimization runs
        
        if success:
            logger.info("Optimization completed successfully!")
            
            # Test the optimized function
            logger.info("Testing the optimized function:")
            for n in [10, 20, 30]:
                if function_name == "fibonacci":
                    result = fibonacci(n)
                    logger.info(f"fibonacci({n}) = {result}")
                elif function_name == "example_function":
                    result = example_function(n)
                    logger.info(f"example_function({n}) = {result}")
                elif function_name == "is_prime":
                    result = is_prime(n)
                    logger.info(f"is_prime({n}) = {result}")
        else:
            logger.warning("Optimization did not improve performance.")
    
    finally:
        # Clean up resources
        logger.info("Cleaning up resources")
        agent.cleanup()
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 