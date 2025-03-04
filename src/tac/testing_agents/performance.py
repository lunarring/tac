import os
import ast
import logging
from typing import Tuple, Optional
from tac.protoblock import ProtoBlock
from tac.core.block_runner import BlockRunner
from tac.utils.project_files import ProjectFiles
from tac.protoblock.factory import ProtoBlockFactory
logger = logging.getLogger(__name__)

class PerformanceTestingAgent:
    """Class responsible for optimizing Python code functions."""
    
    def __init__(self, function_name: str, config):
        """Initialize the code optimizer.
        
        Args:
            function_name: Name of the function to optimize
            config: Configuration object
        """
        self.function_name = self.clean_function_name(function_name)
        self.factory = ProtoBlockFactory()
        self.config = config
        self.project_files = ProjectFiles()
        self.project_files.update_summaries()
        self.codebase = self.project_files.get_codebase_summary()
        
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
            cleaned_name = "unnamed_function"
            
        return cleaned_name

    def check_function_exists(self):
        function_exists, error_msg = self.project_files.get_function_exists(self.function_name)

        if not function_exists:
            logger.error(f"Function {self.function_name} does not exist in the codebase")
            return False
            
        if error_msg:
            logger.error(error_msg)
            return False
        
        return True

    def get_test_function(self):
        test_path = self.config.general.test_path
        test_file = os.path.join(test_path, f"test_performance_{self.function_name}_test.py")
        return test_file

    def optimize(self):
        # Find out if the function exists in the codebase
        assert self.check_function_exists()

        # Find out if we already have a test function for this function
        test_exists = os.path.exists(self.get_test_function())
        
        # If not, create a test function
        if not test_exists:
            self.create_test_function()

        # Run the test function and see how fast it runs!


    def create_test_function(self):
        logger.debug('test function not found, creating it...') 
        task_description = task_description
        test_specification = ""
        test_data_generation = ""
        write_files = [self.fp_func]
        context_files = []
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
        self.factory.save_protoblock(protoblock, self.fp_proto)
        self.protoblock = protoblock


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
    
    
""" 