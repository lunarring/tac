import pytest
from tac.utils.diff_stats import diff_stats

def test_only_additions():
    diff = "+++ b/file.txt\n+New line 1\n+New line 2"
    result = diff_stats(diff)
    # The header line starting with '+++' is ignored.
    assert result['added'] == 2
    assert result['removed'] == 0

def test_only_removals():
    diff = "--- a/file.txt\n-Old line 1\n-Old line 2"
    result = diff_stats(diff)
    # The header line starting with '---' is ignored.
    assert result['added'] == 0
    assert result['removed'] == 2

def test_mix_additions_removals():
    diff = (
        "+++ b/file.txt\n"
        "+Line added 1\n"
        "-Line removed 1\n"
        " Context line\n"
        "+Line added 2\n"
        "--- a/file.txt\n"
        "-Line removed 2"
    )
    result = diff_stats(diff)
    # Only non-header lines starting with '+' and '-' should be counted.
    assert result['added'] == 2
    assert result['removed'] == 2

def test_no_diff():
    diff = "Context line\nAnother context line"
    result = diff_stats(diff)
    assert result['added'] == 0
    assert result['removed'] == 0

def test_plus_lines_not_header():
    diff = "+Some addition not header\n+++This is a header\n+Another addition"
    result = diff_stats(diff)
    # The line starting with '+++This is a header' is treated as a header and skipped.
    assert result['added'] == 2
    assert result['removed'] == 0