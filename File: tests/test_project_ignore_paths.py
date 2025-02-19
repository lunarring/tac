import os
from datetime import datetime
import pytest
from tac.utils.project_files import ProjectFiles
from tac.core.config import config

def test_ignore_paths(tmp_path):
    # Set up directory structure in temporary project directory.
    normal_dir = tmp_path / "normal_dir"
    ignored_dir = tmp_path / "ignored_dir"
    normal_dir.mkdir()
    ignored_dir.mkdir()
    
    # Create a Python file in normal_dir.
    sample_file = normal_dir / "sample.py"
    sample_file.write_text("print('Hello from normal_dir')")
    
    # Create a Python file in ignored_dir.
    ignored_file = ignored_dir / "ignored.py"
    ignored_file.write_text("print('Hello from ignored_dir')")
    
    # Configure ignore_paths to include 'ignored_dir'
    config.general.ignore_paths = ['ignored_dir']
    
    # Initialize ProjectFiles with the temporary directory as project root.
    project_files = ProjectFiles(project_root=str(tmp_path))
    # Run update_summaries with empty exclusions.
    project_files.update_summaries(exclusions=[])
    
    # Retrieve the summaries.
    summaries = project_files.get_all_summaries().get("files", {})
    
    # Assert that sample.py is processed and ignored.py is not.
    assert "normal_dir/sample.py" in summaries, "normal_dir/sample.py should be processed"
    assert "ignored_dir/ignored.py" not in summaries, "ignored_dir/ignored.py should be ignored"
    
if __name__ == "__main__":
    pytest.main([__file__])
