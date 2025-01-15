import pytest
from .main import factorial

# Test cases generated based on specifications:

def test_factorial_positive_cases():
    assert factorial(0) == 1
    assert factorial(5) == 120

def test_factorial_negative_cases():
    with pytest.raises(ValueError):
        factorial(-1)
