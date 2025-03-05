import os
import ast
import json
import logging
from typing import Tuple, Optional, List, Dict, Any
from tac.protoblock import ProtoBlock
from tac.core.block_runner import BlockRunner
from tac.utils.project_files import ProjectFiles
from tac.protoblock.factory import ProtoBlockFactory
from tac.core.log_config import setup_logging
from tac.coding_agents.aider import AiderAgent
from tac.coding_agents.native_agent import NativeAgent
import subprocess
import re
import datetime

logger = setup_logging('tac.trusty_agents.performance')

class PerformanceTestingAgent:
    """Class responsible for optimizing Python code functions."""
    
    def __init__(self, function_name: str, config):
        """Initialize the code optimizer.
        
        Args:
            function_name: Name of the function to optimize
            config: Configuration object
        """
        logger.info("Initializing PerformanceTestingAgent")
        self.config = config
        self.project_files = ProjectFiles()
        self.function_name = self.clean_function_name(function_name)
        self.fp_func = self.project_files.get_function_location(function_name)
        # Check if function location was found
        if not self.fp_func:
            logger.error(f"Function '{function_name}' could not be found in the project.")
            raise ValueError(f"Function '{function_name}' not found. Please provide a valid function name.")
        logger.info(f"Function file path: {self.fp_func}")
        self.fp_test = self.get_test_function(function_name)
        self.factory = ProtoBlockFactory()

        # Create coding agent directly
        if config.general.agent_type == "aider":
            self.agent = AiderAgent(config.raw_config.copy())
        elif config.general.agent_type == "native":
            self.agent = NativeAgent(config.raw_config.copy())
        else:
            raise ValueError(f"Invalid agent type: {config.general.agent_type}")
        
        # List to store test statistics from multiple runs
        self.test_stats: List[Dict[str, Any]] = []
        
    def clean_function_name(self, function_name: str) -> str:
        """Clean the function name by removing brackets, spaces, and other invalid characters.
        
        Args:
            function_name: The raw function name input
            
        Returns:
            A cleaned function name suitable for use in filenames and code
        """
        # Remove parentheses, brackets, spaces and other invalid characters
        cleaned_name = ""
        for char in function_name:
            if char.isalnum() or char == '_':
                cleaned_name += char
        
        # Ensure the function name starts with a letter or underscore
        if cleaned_name and not (cleaned_name[0].isalpha() or cleaned_name[0] == '_'):
            cleaned_name = 'f_' + cleaned_name
            
        # If the name is empty after cleaning, use a default
        if not cleaned_name:
            cleaned_name = "bad_error"
            
        return cleaned_name

    def get_test_function(self, function_name: str):
        test_path = self.config.general.test_path
        test_file = os.path.join(test_path, f"test_performance_{function_name}.py")
        return test_file
    
    def optimize(self, nmb_runs=5):
        """Optimize the function for performance.
        
        Args:
            nmb_runs: Number of optimization attempts to make
            
        Returns:
            bool: True if optimization was successful, False otherwise
        """
        # Run the initial test to establish a baseline
        logger.info(f"Starting performance optimization for {self.function_name}")
        logger.info(f"Running initial tests to establish baseline performance...")
        
        pre_run_success = self.pre_run()
        
        # Check if pre_run was successful
        if not pre_run_success:
            logger.error("Failed to establish baseline performance.")
            logger.error("Please check the logs above for specific errors.")
            return False
        
        # Store the initial performance stats as baseline
        if not self.test_stats:
            logger.error("No baseline performance stats available. Cannot proceed with optimization.")
            return False
            
        baseline_stats = self.test_stats[-1]
        baseline_passed = baseline_stats.get('passed', False)
        baseline_mean_ms = baseline_stats.get('mean_ms', float('inf'))
        
        logger.info(f"Baseline performance: passed={baseline_passed}, mean_ms={baseline_mean_ms:.4f}")
        
        # Create a temporary directory for backups
        import tempfile
        import shutil
        import os
        
        temp_dir = tempfile.mkdtemp(prefix="performance_optimization_")
        logger.debug(f"Created temporary directory for backups: {temp_dir}")
        
        # Make a backup of the original function file
        backup_file = os.path.join(temp_dir, "original.bak")
        shutil.copy2(self.fp_func, backup_file)
        logger.info(f"Created backup of original function")
        
        try:
            for i in range(nmb_runs):
                logger.info(f"Starting optimization run {i+1}/{nmb_runs}")
                
                # Attempt to optimize the function
                self.rewrite_function_agent()
                
                # Run the test function to check correctness and performance
                # Don't update snapshots during optimization runs - we want to compare against the baseline
                passed, performance_stats = self.run_test_function(update_snapshots=False)
                
                # Only keep the optimized version if:
                # 1. The test passes
                # 2. The mean execution time is faster than the previous best
                current_mean_ms = performance_stats.get('mean_ms', float('inf'))
                
                if passed and current_mean_ms < baseline_mean_ms:
                    logger.info(f"Optimization successful: mean_ms improved from {baseline_mean_ms:.4f} to {current_mean_ms:.4f}")
                    # Update the baseline for the next iteration
                    baseline_mean_ms = current_mean_ms
                    baseline_passed = passed
                    # Make a backup of this successful version
                    opt_backup = os.path.join(temp_dir, f"opt_{i+1}.bak")
                    shutil.copy2(self.fp_func, opt_backup)
                else:
                    # Restore the previous best version
                    if not passed:
                        logger.warning(f"Optimization failed: tests did not pass")
                    else:
                        logger.warning(f"Optimization did not improve performance: {current_mean_ms:.4f} ms vs baseline {baseline_mean_ms:.4f} ms")
                    
                    # Restore the previous best version (either the original or the last successful optimization)
                    if i == 0:
                        # Restore from the original backup
                        shutil.copy2(backup_file, self.fp_func)
                        logger.info(f"Restored original function from backup")
                    else:
                        # Find the latest successful optimization backup
                        latest_opt = None
                        for j in range(i, 0, -1):
                            opt_path = os.path.join(temp_dir, f"opt_{j}.bak")
                            if os.path.exists(opt_path):
                                latest_opt = j
                                break
                                
                        if latest_opt:
                            opt_path = os.path.join(temp_dir, f"opt_{latest_opt}.bak")
                            shutil.copy2(opt_path, self.fp_func)
                            logger.info(f"Restored function from optimization run {latest_opt}")
                        else:
                            shutil.copy2(backup_file, self.fp_func)
                            logger.info(f"Restored original function from backup")
            
            # Calculate improvement factor
            initial_baseline = self.test_stats[0].get('mean_ms', float('inf'))
            improvement_factor = initial_baseline / baseline_mean_ms if baseline_mean_ms > 0 else 0
            
            logger.info(f"Optimization complete. Initial performance: {initial_baseline:.4f} ms, Final performance: {baseline_mean_ms:.4f} ms")
            logger.info(f"Code now runs {improvement_factor:.2f}x faster than the original version")
            
            return improvement_factor > 1.0  # Return True if we achieved any improvement
            
        finally:
            # Clean up the temporary directory and all backup files
            try:
                shutil.rmtree(temp_dir)
                logger.debug(f"Removed temporary backup directory: {temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to clean up temporary directory: {str(e)}")

    def pre_run(self):
        """Run initial setup and testing.
        
        Returns:
            bool: True if setup and initial tests succeeded, False otherwise
        """
        # Find out if we already have a test function for this function
        logger.debug(f"Checking if test function exists: {self.fp_test}")
        test_exists = os.path.exists(self.fp_test)
        
        # If not, create a test function
        if not test_exists:
            logger.debug('Test function not found, creating it...')
            try:
                self.create_test_function()
                if not os.path.exists(self.fp_test):
                    logger.error(f"Failed to create test function at {self.fp_test}")
                    return False
            except Exception as e:
                logger.error(f"Error creating test function: {str(e)}")
                return False
        else:
            logger.debug('Test function found, skipping creation...')

        # Run the test function and see how fast it runs!
        # Always update snapshots during pre_run to ensure they match the current implementation
        try:
            logger.info("Running initial tests with snapshot update to ensure snapshots are current")
            passed, performance_stats = self.run_test_function(update_snapshots=True)
        except Exception as e:
            logger.error(f"Error running test function: {str(e)}")
            return False
        
        # Check if we got valid benchmark results
        if not passed:
            logger.error("Initial tests failed. There might be an issue with the function or test implementation.")
            return False
            
        if not performance_stats:
            logger.error("Tests passed but no benchmark results were captured.")
            logger.error("This might be due to missing benchmark fixtures in the test.")
            logger.error("Make sure your test function uses the pytest-benchmark fixture.")
            return False
            
        # Check if we have the essential performance metrics
        if 'mean_ms' not in performance_stats:
            logger.error("Benchmark results are missing essential metrics (mean_ms).")
            logger.error("Make sure your test is properly using the benchmark fixture.")
            return False
            
        logger.info(f"Initial test successful. Mean execution time: {performance_stats.get('mean_ms', 0):.4f} ms")
        return True

    def create_test_function(self):
        protoblock = self.get_protoblock_test_function()
        self.agent.run(protoblock)

    def rewrite_function_agent(self):
        protoblock = self.get_protoblock_performance_optimization()
        self.agent.run(protoblock)


    def get_protoblock_performance_optimization(self):
            task_description = f"""We want to optimize the performance of the {self.function_name} function. Importantly, the runtime of the function should be massively reduced, while the output should remain the same, see the test function in {self.fp_test}. You can use any method you want to optimize the function, but you need to make sure that the output of the function is the same as the original version, and you can remove unncecessary code.
        """
            test_specification = "No tests need to be written, we are only optimizing the function"
            test_data_generation = "No test data generation needed"
            write_files = [self.fp_func]
            context_files = [self.fp_test]
            commit_message = "None"
            test_results = None

            protoblock = ProtoBlock(
                task_description,
                test_specification,
                test_data_generation,
                write_files,
                context_files,
                commit_message,
                test_results,
            )

            return protoblock

    def get_protoblock_test_function(self):
        task_description = f"""Generate a test function for the {self.function_name} function. The test HAS to have the following properties:
    - Use the pytest.mark.performance decorator to mark it as a performance test
    - Use pytest's benchmark fixture to measure the performance of the function
    - Use snapshot testing to verify the correctness of the function output
    - Create appropriate test input data that exercises the function's capabilities
    - The test function name should follow the pattern test_{self.function_name}_output_snapshot
    - The test should call the benchmark fixture with the function and input data
    - Use snapshot.assert_match() to compare the output with the stored snapshot
    - Convert any numpy arrays to lists before snapshot comparison using .tolist()
    - Include necessary imports (pytest, numpy, etc.). Here is an example:
    
@pytest.mark.performance
def test_bubu_output_snapshot(benchmark, snapshot):
    input_arr = np.array([[0, np.pi/4], [np.pi/2, np.pi]])
    # Run bubu with the benchmark fixture
    output = benchmark(bubu, input_arr)
    # Assert that the output matches the stored snapshot
    snapshot.assert_match(output.tolist())
    
    """
        test_specification = "we are only writing a test function, nothing else"
        test_data_generation = f"""you need to have a careful look at {self.function_name} and decide what is a valid and reasonable input for the test function."""
        write_files = [self.fp_test]
        context_files = [self.fp_func]
        commit_message = "None"
        test_results = None

        protoblock = ProtoBlock(
            task_description,
            test_specification,
            test_data_generation,
            write_files,
            context_files,
            commit_message,
            test_results,
        )

        return protoblock

    def run_test_function(self, update_snapshots=False):
        """Run the test function and extract performance statistics.
        
        Args:
            update_snapshots: Whether to update snapshots during this test run
        
        Returns:
            Tuple[bool, dict]: A tuple containing:
                - bool: Whether the tests passed (True) or failed (False)
                - dict: Performance statistics from the benchmark
        """
        
        logger.debug(f'Running test function: {self.fp_test}')
        
        # Create a temporary file for the benchmark JSON output
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
            json_output_path = tmp.name
        
        try:
            # Run pytest with benchmark and JSON output
            cmd = [
                "pytest", 
                self.fp_test, 
                "-v", 
                "--benchmark-json", json_output_path
            ]
            
            # Add snapshot update flag if requested
            if update_snapshots:
                cmd.append("--snapshot-update")
                logger.info("Running tests with snapshot update")
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            # Check if tests passed
            passed = "FAILED" not in result.stdout and result.returncode == 0
            
            # Extract performance statistics
            performance_stats = {}
            
            # Parse benchmark results from JSON file if tests passed
            if passed and os.path.exists(json_output_path):
                try:
                    import json
                    with open(json_output_path, 'r') as f:
                        benchmark_data = json.load(f)
                    
                    # Extract benchmark data from the JSON
                    if 'benchmarks' in benchmark_data and benchmark_data['benchmarks']:
                        benchmark = benchmark_data['benchmarks'][0]  # Get the first benchmark
                        
                        # Convert time to milliseconds if needed
                        # pytest-benchmark reports times in seconds
                        time_unit = benchmark.get('unit', 'seconds')
                        time_factor = 1000.0  # Convert to milliseconds
                        
                        performance_stats = {
                            'name': benchmark.get('name', 'unknown'),
                            'min_ms': benchmark.get('stats', {}).get('min', 0) * time_factor,
                            'max_ms': benchmark.get('stats', {}).get('max', 0) * time_factor,
                            'mean_ms': benchmark.get('stats', {}).get('mean', 0) * time_factor,
                            'stddev': benchmark.get('stats', {}).get('stddev', 0) * time_factor,
                            'median': benchmark.get('stats', {}).get('median', 0) * time_factor,
                            'iqr': benchmark.get('stats', {}).get('iqr', 0) * time_factor,
                            'outliers': str(benchmark.get('stats', {}).get('outliers', '')),
                            'ops': benchmark.get('stats', {}).get('ops', 0),
                            'rounds': benchmark.get('stats', {}).get('rounds', 0),
                            'iterations': benchmark.get('stats', {}).get('iterations', 0),
                            'timestamp': datetime.datetime.now().isoformat(),
                            'passed': passed
                        }
                        
                        # Store the test statistics in our list
                        self.test_stats.append(performance_stats)
                        logger.debug(f"Added performance stats: {performance_stats}")
                    else:
                        logger.warning("No benchmark data found in the JSON output")
                except Exception as e:
                    logger.error(f"Error parsing benchmark JSON: {str(e)}")
            elif passed:
                logger.warning("Tests passed but no benchmark JSON file was created")
            
            # Log the results
            if passed:
                logger.info(f"Test passed with performance stats: {performance_stats}")
                logger.info(f"Total runs recorded: {len(self.test_stats)}")
            else:
                logger.error(f"Test failed. Output: {result.stdout}")
                logger.error(f"Error: {result.stderr}")
            
            return passed, performance_stats
        
        finally:
            # Clean up the temporary JSON file
            if os.path.exists(json_output_path):
                try:
                    os.unlink(json_output_path)
                except Exception as e:
                    logger.warning(f"Failed to delete temporary JSON file: {str(e)}")
        


    """
all the things for tomorrow:
we wanna make a snapshottest and use the right marker!

from snapshottest import TestCase

@pytest.mark.performance
class TestBubu(TestCase):
    def test_bubu_output_snapshot(self):
        input_arr = np.array([[0, np.pi/4], [np.pi/2, np.pi]])
        output = bubu(input_arr)
        # Assert that the output matches the stored snapshot
        self.assertMatchSnapshot(output.tolist())

------
figure out how does it work with snapshotting
figure out how to combine with benchmarking

then move on to make another protoblock for performance optimization.
then run benchmark again and again


TO KEEP IN MIND:

snapshot tests are in:
tests/snapshot/snap_test_performance_bubu.py


FIXTURE: for running class that need set up (integrate later)
import pytest
from my_module import MyClass

# This fixture creates an instance of MyClass with any necessary initialization.
@pytest.fixture
def my_instance():
    instance = MyClass(param=42)
    instance.setup()  # Perform additional setup if needed.
    return instance

def test_my_method(my_instance):
    result = my_instance.my_method()
    assert result == expected_value
""" 