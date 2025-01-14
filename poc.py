import pytest
import textwrap
import importlib
import subprocess

# ------------------------------------------------
# 1. Simulate Text Inputs
# ------------------------------------------------

instructions = """
Change the function is_divisible_by_two so it returns True for even numbers and False for odd numbers.
"""

test_specification = """
We will create two test functions:
1) test_divisible_by_two_positive_cases(): checks even numbers (2, 4) return True.
2) test_divisible_by_two_negative_cases(): checks odd numbers (3, 5) return False.
"""

test_data_generation = """
Positive data: 2, 4
Negative data: 3, 5
"""

# ------------------------------------------------
# 2. Create a Minimal Starting Code (Fails the Tests)
# ------------------------------------------------

initial_code = textwrap.dedent("""\
def is_divisible_by_two(num):
    return False
""")

# Ensure the file is properly written and flushed
with open("my_module.py", "w", encoding="utf-8") as f:
    f.write(initial_code)
    f.flush()
    import os
    os.fsync(f.fileno())

# ------------------------------------------------
# 3. Generate the Test File Based on Specification
# ------------------------------------------------

test_code = textwrap.dedent(f"""\
import pytest
from my_module import is_divisible_by_two

# Test specification described as:

def test_divisible_by_two_positive_cases():
    assert is_divisible_by_two(2) == True
    assert is_divisible_by_two(4) == True

def test_divisible_by_two_negative_cases():
    assert is_divisible_by_two(3) == False
    assert is_divisible_by_two(5) == False
""")

with open("test_code.py", "w", encoding="utf-8") as f:
    f.write(test_code)

# ------------------------------------------------
# 4. Helper Function: Run Pytest In-Process
# ------------------------------------------------

def run_tests_in_process():
    """
    Runs pytest as a separate process to avoid module caching issues
    """
    result = subprocess.run(['pytest', 'test_code.py', '--maxfail=1', '--disable-warnings'], 
                          capture_output=True, text=True)
    print(result.stdout)
    print(result.stderr)
    return result.returncode

# ------------------------------------------------
# 5. Check That the Test Fails Initially
# ------------------------------------------------

print("=== Step 1: Initial Tests (Should Fail) ===")
initial_exit_code = run_tests_in_process()

if initial_exit_code == 0:
    print("ERROR: Tests passed unexpectedly. Our 'unimplemented' code isn't supposed to pass.")
else:
    print("As expected, tests failed because the code is not implemented yet.\n")

# ------------------------------------------------
# 6. Simulate a “Coding Agent” Fixing the Code
# ------------------------------------------------

print("=== Step 2: Applying Changes According to Instructions ===")
print("Instructions given to the coding agent:", instructions.strip(), "\n")

fixed_code = textwrap.dedent("""\
def is_divisible_by_two(num):
    return (num % 2) == 0
""")

# Ensure the file is properly written and flushed
with open("my_module.py", "w", encoding="utf-8") as f:
    f.write(fixed_code)
    f.flush()
    import os
    os.fsync(f.fileno())

# ------------------------------------------------
# 7. Re-run the Tests to Confirm They Now Pass
# ------------------------------------------------

print("=== Step 3: Tests After Fix (Should Pass) ===")
final_exit_code = run_tests_in_process()

if final_exit_code == 0:
    print("Success: The tests now pass with the updated code.")
else:
    print("ERROR: The tests still fail. Further debugging is required.")