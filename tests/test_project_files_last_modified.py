import os
import time
import json
from datetime import datetime
import tempfile
import pytest

from tac.utils.project_files import ProjectFiles

def test_last_modified_field(tmp_path):
    # Setup temporary project root directory
    project_root = tmp_path / "project"
    project_root.mkdir()

    # Create a test Python file in the temporary project root
    test_file = project_root / "test.py"
    test_file.write_text("print('Hello, world!')")

    # Initialize ProjectFiles with the temporary project root
    pf = ProjectFiles(project_root=str(project_root))
    pf.update_summaries()

    # Load the generated summary file (.tac_project_files.json)
    summary_file = project_root / ".tac_project_files.json"
    assert summary_file.exists(), "Summary file was not created."

    with summary_file.open("r") as f:
        data = json.load(f)

    rel_path = os.path.relpath(str(test_file), str(project_root))
    assert rel_path in data["files"], "Test file summary is missing."
    assert "last_modified" in data["files"][rel_path], "last_modified field is missing in the file summary."
    first_timestamp = data["files"][rel_path]["last_modified"]

    # Sleep to ensure a difference in the modification timestamp
    time.sleep(1)

    # Modify the file content to update its last modification time
    test_file.write_text("print('Hello, modified!')")
    pf.update_summaries()

    with summary_file.open("r") as f:
        data = json.load(f)

    assert rel_path in data["files"], "Test file summary is missing after update."
    assert "last_modified" in data["files"][rel_path], "last_modified field is missing after update."
    second_timestamp = data["files"][rel_path]["last_modified"]

    dt1 = datetime.fromisoformat(first_timestamp)
    dt2 = datetime.fromisoformat(second_timestamp)
    assert dt2 > dt1, "The last_modified timestamp was not updated after modifying the file."
    
if __name__ == "__main__":
    pytest.main()