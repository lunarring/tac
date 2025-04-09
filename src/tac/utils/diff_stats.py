def diff_stats(diff_output: str) -> dict:
    """
    Parse the given git diff output string and return a dictionary with counts of added and removed lines.
    This function ignores diff header lines that start with '+++' or '---'.

    Args:
        diff_output (str): The diff output string from git.

    Returns:
        dict: A dictionary in the form {'added': int, 'removed': int}
    """
    added = 0
    removed = 0
    for line in diff_output.splitlines():
        # Skip header lines starting with '+++' or '---'
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return {'added': added, 'removed': removed}


if __name__ == '__main__':
    # Example usage for manual testing
    sample_diff = """diff --git a/file.txt b/file.txt
--- a/file.txt
+++ b/file.txt
@@ -1,3 +1,3 @@
-Hello World
+Hello Universe
 This is a test"""
    result = diff_stats(sample_diff)
    print(result)