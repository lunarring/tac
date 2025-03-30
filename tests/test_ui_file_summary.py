import pytest
from tac.web import ui
from tac.utils.project_files import ProjectFiles

class DummyProjectFiles:
    def get_all_summaries(self):
        return {
            "files": {
                "dummy.py": {
                    "summary_high_level": "High level info",
                    "summary_detailed": "Detailed info"
                },
                "error_file.py": {
                    "error": "Analysis failed"
                },
                "no_summary.py": {}
            }
        }

def dummy_get_all_summaries(self):
    return DummyProjectFiles().get_all_summaries()

@pytest.fixture(autouse=True)
def patch_project_files(monkeypatch):
    monkeypatch.setattr(ProjectFiles, "get_all_summaries", dummy_get_all_summaries)

def test_load_high_level_summaries():
    result = ui.load_high_level_summaries()
    # Check that dummy.py shows only high level info and does not include detailed info
    assert "High level info" in result
    assert "Detailed info" not in result
    # Check that error_file.py shows the error message
    assert "Error analyzing file: Analysis failed" in result
    # Check that no_summary.py defaults to "No summary available"
    assert "No summary available" in result