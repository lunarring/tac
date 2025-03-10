import os
import ast
import json
import logging
import tempfile
import shutil
from typing import Tuple, Optional, List, Dict, Any
# Fix circular import by importing directly from specific modules
from tac.blocks.model import ProtoBlock
from tac.blocks.processor import BlockProcessor
from tac.blocks.generator import ProtoBlockGenerator
from tac.utils.project_files import ProjectFiles
from tac.core.log_config import setup_logging
from tac.coding_agents.aider import AiderAgent
from tac.coding_agents.native_agent import NativeAgent
from tac.utils.git_manager import FakeGitManager
from tac.trusty_agents.base import TrustyAgent
import subprocess
import re
import datetime
import contextlib
import io

logger = setup_logging('tac.trusty_agents.performance')

class PerformanceTestingAgent(TrustyAgent):
    """Class responsible for optimizing Python code functions."""
    
    def __init__(self, function_name: str = None, config = None):
        """Initialize the code optimizer.
        
        Args:
            function_name: Name of the function to optimize
            config: Configuration object
        """
        logger.info("Initializing PerformanceTestingAgent")
        
        # Only initialize the full agent if function_name and config are provided
        if function_name and config:
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
            self.factory = ProtoBlockGenerator()
            
            # Set up git manager (always use FakeGitManager for performance testing)
            logger.info("Using FakeGitManager for performance testing")
            # Initialize FakeGitManager with the current directory and set cleanup_temp_dir to True
            self.git_manager = FakeGitManager(repo_path='.', cleanup_temp_dir=False)
            self.temp_dir = self.git_manager.temp_dir

            # Create coding agent directly
            if config.general.agent_type == "aider":
                self.agent = AiderAgent(config.raw_config.copy())
                # Inject FakeGitManager into the agent
                if hasattr(self.agent, 'git_manager'):
                    self.agent.git_manager = self.git_manager
            elif config.general.agent_type == "native":
                self.agent = NativeAgent(config.raw_config.copy())
                # Inject FakeGitManager into the agent
                if hasattr(self.agent, 'git_manager'):
                    self.agent.git_manager = self.git_manager
            else:
                raise ValueError(f"Invalid agent type: {config.general.agent_type}")
            
            # List to store test statistics from multiple runs
            self.test_stats: List[Dict[str, Any]] = []
        else:
            logger.info("Initialized PerformanceTestingAgent in base mode (no function specified)")
    
    def _check_impl(self, protoblock: ProtoBlock, codebase: Dict[str, str], code_diff: str) -> Tuple[bool, str, str]:
        """
        Check the implementation for performance issues.
        
        Args:
            protoblock: The ProtoBlock containing task specifications
            codebase: Dictionary mapping file paths to their contents
            code_diff: The git diff showing implemented changes
            
        Returns:
            Tuple containing:
            - bool: Success status (True if performance is acceptable, False otherwise)
            - str: Error analysis (empty string if success is True)
            - str: Failure type description (empty string if success is True)
        """
        logger.info("Performance check not yet implemented")
        # For now, always return success since this agent is not fully implemented
        # In the future, this would analyze the code for performance issues
        return True, "", ""
    
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
    
    def optimize(self, nmb_runs=1):
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
        
        # The initial commit was already made in pre_run
        # We'll use this to restore if optimization fails
        initial_commit = "initial_commit"
        
        # Track the best optimization
        best_optimization_commit = initial_commit
        best_mean_ms = baseline_mean_ms
        optimization_succeeded = False
        
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
                
                if passed and current_mean_ms < best_mean_ms:
                    # Calculate speedup factor from the previous best
                    speedup_factor = best_mean_ms / current_mean_ms if current_mean_ms > 0 else float('inf')
                    logger.info(f"Optimization successful: {speedup_factor:.2f}x speedup ({best_mean_ms:.4f} ms → {current_mean_ms:.4f} ms)")
                    
                    # Update the best metrics
                    best_mean_ms = current_mean_ms
                    optimization_succeeded = True
                    
                    # "Commit" the changes in the fake git manager
                    optimization_commit = f"run_{i+1}"
                    self.git_manager.commit(optimization_commit)
                    best_optimization_commit = optimization_commit
                else:
                    # Restore the previous best version
                    if not passed:
                        logger.warning(f"Optimization failed: tests did not pass")
                    else:
                        logger.warning(f"Optimization did not improve performance: {current_mean_ms:.4f} ms vs best {best_mean_ms:.4f} ms")
                    
                    # Restore to the best version so far
                    self.git_manager.restore_commit(best_optimization_commit)
                    logger.info(f"Restored to best version: {best_optimization_commit}")
            
            # Final performance comparison - calculate speedup from baseline
            if baseline_mean_ms > 0 and best_mean_ms > 0:
                # Calculate overall speedup factor from the baseline
                baseline_speedup = baseline_mean_ms / best_mean_ms
                
                # Format the speedup message
                if baseline_speedup > 1:
                    speedup_msg = f"{baseline_speedup:.2f}x faster than baseline"
                else:
                    # In case optimization made things worse
                    slowdown = 1 / baseline_speedup
                    speedup_msg = f"{slowdown:.2f}x slower than baseline"
                
                logger.info(f"Optimization complete. Final result: {speedup_msg}")
                logger.info(f"Baseline execution time: {baseline_mean_ms:.4f} ms")
                logger.info(f"Best execution time: {best_mean_ms:.4f} ms")
            else:
                logger.info("Could not calculate speedup due to invalid timing values")
            
            # If optimization succeeded, keep the best version
            # Otherwise, revert to the original state
            if optimization_succeeded and best_optimization_commit != initial_commit:
                logger.info(f"Keeping optimized version: {best_optimization_commit}")
                # Make sure we're on the best version
                self.git_manager.restore_commit(best_optimization_commit)
                
                # Report the final speedup in the success message
                if baseline_mean_ms > 0 and best_mean_ms > 0:
                    baseline_speedup = baseline_mean_ms / best_mean_ms
                    logger.info(f"Optimized function has been applied to your codebase ({baseline_speedup:.2f}x faster than baseline)")
                else:
                    logger.info("Optimized function has been applied to your codebase")
            else:
                logger.info("No successful optimization found, reverting to original state")
                self.git_manager.restore_commit(initial_commit)
                logger.info("Original function state restored")
            
            # Return the optimization results
            return optimization_succeeded
            
        except Exception as e:
            logger.error(f"Error during optimization: {e}")
            # Revert to original state in case of error
            self.git_manager.restore_commit(initial_commit)
            logger.info("Original function state restored due to error")
            return False
            
        finally:
            # We don't clean up the temporary directory here
            # It will be cleaned up when the cleanup() method is called
            logger.debug(f"Keeping FakeGitManager temporary directory for later use: {self.temp_dir}")
            
            # No need for final verification - FakeGitManager already handles file operations
            # when we call restore_commit

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

        # Remove print statements from the function to reduce output during benchmarking
        # First run: Generate a snapshot
        try:
            logger.info("Running initial tests with snapshot update to generate baseline snapshot")
            passed_first, performance_stats_first = self.run_test_function(update_snapshots=True)
        except Exception as e:
            logger.error(f"Error running test function (first run): {str(e)}")
            return False
        
        # Check if the first run passed
        if not passed_first:
            logger.error("Initial tests failed. There might be an issue with the function or test implementation.")
            return False
            
        if not performance_stats_first:
            logger.error("Tests passed but no benchmark results were captured.")
            logger.error("This might be due to missing benchmark fixtures in the test.")
            logger.error("Make sure your test function uses the pytest-benchmark fixture.")
            return False
        
        # Second run: Verify against the snapshot (without updating)
        # This will detect if the function has random behavior
        try:
            logger.info("Running tests a second time to check for randomness in the function output")
            passed_second, performance_stats_second = self.run_test_function(update_snapshots=False)
        except Exception as e:
            logger.error(f"Error running test function (second run): {str(e)}")
            return False
        
        # Check if the second run passed
        if not passed_second:
            logger.error("RANDOMNESS DETECTED: The function appears to produce different outputs on each run.")
            logger.error("This will make performance optimization unreliable.")
            logger.error("Please modify the function to use a fixed random seed or remove randomness before optimizing.")
            return False
            
        # Check if we have the essential performance metrics
        if 'mean_ms' not in performance_stats_first:
            logger.error("Benchmark results are missing essential metrics (mean_ms).")
            logger.error("Make sure your test is properly using the benchmark fixture.")
            return False
            
        # Store the test stats from the first run
        self.test_stats = [performance_stats_first]
        
        logger.info(f"Initial tests successful. Mean execution time: {performance_stats_first.get('mean_ms', 0):.4f} ms")
        logger.info("Function output is consistent across runs (no randomness detected)")
        
        # Make an initial commit to the FakeGitManager
        # This will be used as the baseline for comparison
        logger.info("Making initial commit to FakeGitManager")
        self.git_manager.commit("initial_commit")
        
        return True

    def create_test_function(self):
        protoblock = self.get_protoblock_test_function()
        self.agent.run(protoblock)

    def rewrite_function_agent(self):
        protoblock = self.get_protoblock_performance_optimization()
        self.agent.run(protoblock)


    def get_protoblock_performance_optimization(self):
            # First, get line profiling results
            profiling_results = self.profile_function()
            
            task_description = f"""We want to optimize the performance of the {self.function_name} function. Importantly, the runtime of the function should be reduced, while the output should remain the same, see the test function in {self.fp_test}. You can use any method you want to optimize the function, but you need to make sure that the output of the function is the same as the original version, and you can remove unncecessary code. Be careful however, the critical thing is that we pass the test function, and keep in mind we are running this iteratively, so pick something that is likely to have a big impact and is safe.

Additionally, here the line profiling results for the function to identify the bottlenecks:
{profiling_results}
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
    - The input data to test the function should be generated in the test function and be completely reproducible.
    - Use realistic sizes for the input data, don't make it too small or too big
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
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
            json_output_path = tmp.name
        
        try:
            # Run pytest with benchmark and JSON output
            cmd = [
                "pytest", 
                self.fp_test, 
                "-v",  # Verbose flag for test results
            ]
            
            # Only add quiet flags if we're not updating snapshots
            # This ensures we see output during initial test runs
            if not update_snapshots:
                cmd.extend([
                    "-q",  # Quiet flag to reduce output
                    "--no-header",  # Suppress header
                    "--no-summary",  # Suppress summary
                    "--benchmark-quiet",  # Suppress benchmark output
                ])
            
            # Add benchmark JSON output
            cmd.extend(["--benchmark-json", json_output_path])
            
            # Add snapshot update flag if requested
            if update_snapshots:
                cmd.append("--snapshot-update")
                logger.info("Running tests with snapshot update")
            
            # Only suppress stdout if we're not updating snapshots
            if not update_snapshots:
                with contextlib.redirect_stdout(io.StringIO()):
                    result = subprocess.run(cmd, capture_output=True, text=True)
            else:
                # For initial runs, show the output
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
                logger.info(f"Total successful runs recorded: {len(self.test_stats)}")
            else:
                # For failed tests, show the full output to help diagnose the issue
                logger.error(f"Test failed. Output: {result.stdout}")
                
                # If there's error output, show that too
                if result.stderr:
                    logger.error(f"Error output: {result.stderr}")
            
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

    def cleanup(self):
        """Clean up resources used by the PerformanceTestingAgent.
        
        This method should be called when you're done with the agent to clean up
        any temporary directories or resources it created.
        """
        if self.git_manager:
            try:
                logger.info("Cleaning up FakeGitManager resources")
                # FakeGitManager doesn't have a cleanup method, but it will clean up
                # its temp directory when garbage collected if cleanup_temp_dir is True.
                # We can force cleanup by manually removing the temp directory
                if hasattr(self.git_manager, 'temp_dir') and self.git_manager.temp_dir and os.path.exists(self.git_manager.temp_dir):
                    logger.info(f"Manually cleaning up temporary directory: {self.git_manager.temp_dir}")
                    shutil.rmtree(self.git_manager.temp_dir)
                    self.git_manager.temp_dir = None
                    self.temp_dir = None
            except Exception as e:
                logger.warning(f"Failed to clean up FakeGitManager resources: {str(e)}")
        
        logger.info("PerformanceTestingAgent cleanup complete")

    def profile_function(self):
        """
        Performs line-wise profiling of the function in fp_func.
        
        Returns:
            str: Formatted line profiling results similar to line_profiler output
        """
        logger.info(f"Performing line-wise profiling of {self.function_name}")
        
        # Create a temporary directory for profiling
        with tempfile.TemporaryDirectory() as temp_dir:
            # Copy the function file to the temp directory
            func_filename = os.path.basename(self.fp_func)
            temp_func_path = os.path.join(temp_dir, func_filename)
            shutil.copy2(self.fp_func, temp_func_path)
            
            # Copy the test file to the temp directory
            test_filename = os.path.basename(self.fp_test)
            temp_test_path = os.path.join(temp_dir, test_filename)
            shutil.copy2(self.fp_test, temp_test_path)
            
            # Create a wrapper script that imports the function and runs it with the @profile decorator
            wrapper_path = os.path.join(temp_dir, "profile_wrapper.py")
            
            # Create the wrapper script
            with open(wrapper_path, 'w') as f:
                f.write(f"""
import os
import sys
import time
import importlib.util
from line_profiler import LineProfiler
import contextlib
import io

# Redirect stdout to suppress function output
@contextlib.contextmanager
def suppress_stdout():
    # Save the original stdout
    original_stdout = sys.stdout
    # Create a dummy file-like object to capture output
    dummy_stdout = io.StringIO()
    # Redirect stdout to the dummy file
    sys.stdout = dummy_stdout
    try:
        yield dummy_stdout
    finally:
        # Restore the original stdout
        sys.stdout = original_stdout

# Add the current directory and parent directories to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the module containing the function
spec = importlib.util.spec_from_file_location("{os.path.splitext(func_filename)[0]}", "{temp_func_path}")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

# Get the function
func = getattr(module, "{self.function_name}")

# Create a LineProfiler
profile = LineProfiler()

# Wrap the function with the profile decorator
profiled_func = profile(func)

# Import the test module to get test data
test_spec = importlib.util.spec_from_file_location("{os.path.splitext(test_filename)[0]}", "{temp_test_path}")
test_module = importlib.util.module_from_spec(test_spec)
test_spec.loader.exec_module(test_module)

# Variables to store test data
test_args = []
test_kwargs = {{}}
captured_args = []
captured_kwargs = {{}}

# Create a mock function to capture arguments
def mock_func(*args, **kwargs):
    global captured_args, captured_kwargs
    captured_args = args
    captured_kwargs = kwargs
    # Return a dummy value to prevent errors
    return "mock_result"

# Try to find a function that creates test data
found_test_data = False

# First, try to find a test function that calls our target function
for name in dir(test_module):
    if name.startswith('test_') and '{self.function_name}' in name:
        test_func = getattr(test_module, name)
        
        # Temporarily replace the real function with our mock
        original_func = getattr(module, "{self.function_name}")
        setattr(module, "{self.function_name}", mock_func)
        
        try:
            # Run the test function to capture the arguments
            with suppress_stdout():
                test_func()
            # Check if we captured any arguments
            if captured_args or captured_kwargs:
                test_args = captured_args
                test_kwargs = captured_kwargs
                print(f"Successfully extracted test data from {{name}}")
                found_test_data = True
                break
        except Exception as e:
            print(f"Error running test function {{name}}: {{e}}")
        finally:
            # Restore the original function
            setattr(module, "{self.function_name}", original_func)

# If we couldn't get test data from the test function, try to create appropriate test data
if not found_test_data:
    print("Could not extract test data from test functions, attempting to create test data")
    
    # Try to infer the expected input type from the function body
    import inspect
    import re
    
    # Get the function source code
    func_source = inspect.getsource(func)
    
    # Check for common patterns that indicate the expected input type
    if "numpy" in func_source or "np." in func_source:
        print("Function appears to use numpy arrays")
        
        # Check for shape references
        shape_matches = re.findall(r'(\w+)\.shape', func_source)
        if shape_matches:
            param_name = shape_matches[0]
            print(f"Function expects a numpy array with shape attribute in parameter {{param_name}}")
            
            # Try to create a small numpy array
            try:
                import numpy as np
                # Create a small 3D array (common for image processing)
                test_args = [np.zeros((10, 10, 3))]
                print(f"Created test numpy array with shape {{test_args[0].shape}}")
            except ImportError:
                print("Could not import numpy, using fallback test data")
                test_args = [1]  # Fallback
    else:
        # For other types, use simple defaults based on parameter names
        sig = inspect.signature(func)
        for param_name, param in sig.parameters.items():
            # Try to infer type from parameter name
            if "str" in param_name.lower() or "name" in param_name.lower() or "path" in param_name.lower():
                test_args.append("test_string")
            elif "int" in param_name.lower() or "count" in param_name.lower() or "num" in param_name.lower():
                test_args.append(1)
            elif "float" in param_name.lower() or "val" in param_name.lower():
                test_args.append(1.0)
            elif "list" in param_name.lower() or "array" in param_name.lower():
                test_args.append([1, 2, 3])
            elif "dict" in param_name.lower() or "map" in param_name.lower():
                test_args.append({{"key": "value"}})
            elif "bool" in param_name.lower() or "flag" in param_name.lower():
                test_args.append(True)
            else:
                # Default fallback
                test_args.append(None)

# Run the profiled function with the test data
success = False
try:
    print(f"Running profiled function with args: {{test_args}} and kwargs: {{test_kwargs}}")
    # Suppress output during profiling
    with suppress_stdout():
        result = profiled_func(*test_args, **test_kwargs)
    print(f"Function executed successfully, result type: {{type(result)}}")
    success = True
except Exception as e:
    print(f"Error running profiled function: {{e}}")
    # If we get an error, try one more approach - look for test data in the test file
    try:
        # Look for variables in the test module that might be test data
        for name in dir(test_module):
            if not name.startswith('__') and not callable(getattr(test_module, name)):
                value = getattr(test_module, name)
                # Try using this as test data
                print(f"Trying {{name}} as test data, type: {{type(value)}}")
                try:
                    with suppress_stdout():
                        result = profiled_func(value)
                    print(f"Success using {{name}} as test data!")
                    success = True
                    break
                except Exception as inner_e:
                    print(f"Error with {{name}}: {{inner_e}}")
    except Exception as outer_e:
        print(f"Failed to find usable test data: {{outer_e}}")

# If all attempts failed, try with a numpy array as a last resort for image processing functions
if not success and ("image" in func_source.lower() or "img" in func_source.lower()):
    try:
        import numpy as np
        print("Trying with different numpy array shapes as last resort")
        
        # Try different common shapes for image data
        shapes = [(10, 10), (10, 10, 1), (10, 10, 3), (10, 10, 4)]
        for shape in shapes:
            try:
                print(f"Trying numpy array with shape {{shape}}")
                test_array = np.zeros(shape)
                with suppress_stdout():
                    result = profiled_func(test_array)
                print(f"Success with shape {{shape}}!")
                success = True
                break
            except Exception as e:
                print(f"Failed with shape {{shape}}: {{e}}")
    except ImportError:
        print("Could not import numpy for last resort attempt")

# Print the profiling results to a string
import io
output = io.StringIO()
if success:
    profile.print_stats(stream=output)
    print(output.getvalue())
else:
    print("Failed to profile function with any test data")
    output.write("Failed to profile function with any test data")
""")
            
            # Install line_profiler if not already installed
            try:
                subprocess.run(["pip", "install", "line_profiler"], check=True, capture_output=True)
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to install line_profiler: {e}")
                return "Error: Failed to install line_profiler"
            
            # Run the wrapper script
            try:
                result = subprocess.run(
                    ["python", wrapper_path], 
                    check=True, 
                    capture_output=True,
                    text=True
                )
                
                # Extract just the line profiler output from the result
                output_lines = result.stdout.split('\n')
                profiler_output_start = None
                
                # Find where the line profiler output starts
                for i, line in enumerate(output_lines):
                    if line.startswith('Timer unit:'):
                        profiler_output_start = i
                        break
                
                if profiler_output_start is not None:
                    # Return only the line profiler output
                    return '\n'.join(output_lines[profiler_output_start:])
                else:
                    # If we can't find the profiler output, return the full output
                    return result.stdout
                
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to run profiling: {e}")
                logger.error(f"Stderr: {e.stderr}")
                
                # If profiling failed, return a more user-friendly error message
                error_msg = f"""
Error: Failed to run profiling

{e.stderr}

The profiling failed, likely because we couldn't determine the correct test data for the function.
You can still proceed with optimization without the profiling results.
"""
                return error_msg 