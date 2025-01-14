import pytest
from my_module import is_divisible_by_two

# Test specification described as:

def test_divisible_by_two_positive_cases():
    assert is_divisible_by_two(2) == True
    assert is_divisible_by_two(4) == True

def test_divisible_by_two_negative_cases():
    assert is_divisible_by_two(3) == False
    assert is_divisible_by_two(5) == False
