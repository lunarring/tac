import os
import shutil
import logging

logger = logging.getLogger('tac.utils.filesystem')

def cleanup_nested_tests():
    """
    Cleanup nested test directory by moving files from tests/tests/ to tests/
    and removing the tests/tests directory if it exists.
    
    This utility function helps prevent the creation of nested test directories
    which can cause issues with test discovery and execution.
    """
    nested_tests_dir = os.path.join('tests', 'tests')
    if not os.path.exists(nested_tests_dir):
        return

    logger.info("Found nested tests directory. Moving files to parent directory...")
    
    try:
        # Move all files from tests/tests to tests
        for item in os.listdir(nested_tests_dir):
            src_path = os.path.join(nested_tests_dir, item)
            dst_path = os.path.join('tests', item)
            
            if os.path.isfile(src_path):
                # If destination exists, remove it first
                if os.path.exists(dst_path):
                    os.remove(dst_path)
                    logger.info(f"Removed existing file {item} in tests/")
                
                os.rename(src_path, dst_path)
                logger.info(f"Moved {item} to tests/")
        
        # Force remove the tests/tests directory and all its contents
        shutil.rmtree(nested_tests_dir)
        logger.info("Removed nested tests directory and all its contents")
        
    except Exception as e:
        logger.error(f"Error during test directory cleanup: {str(e)}") 