import string
import pytest
from tac.utils.random_string import generate_random_string

def test_alphanumeric_only():
    # Generate a random string with the default configuration
    result = generate_random_string(50)
    # Check that every character is alphanumeric
    for char in result:
        assert char.isalnum(), f"Character {char} is not alphanumeric in string: {result}"

def test_include_symbols_allowed_set():
    # Define the allowed set when symbols are included
    allowed_chars = set(string.ascii_letters + string.digits + string.punctuation)
    
    # Generate a random string with symbols allowed
    result = generate_random_string(50, include_symbols=True)
    # Check that every character is in the allowed set
    for char in result:
        assert char in allowed_chars, f"Character {char} is not in the allowed set."

def test_includes_symbol_when_requested():
    # Generate a longer random string to increase probability of including a symbol
    result = generate_random_string(200, include_symbols=True)
    # Check that at least one character is a punctuation symbol
    punctuation_set = set(string.punctuation)
    symbols_in_result = set(result) & punctuation_set
    assert symbols_in_result, f"Generated string did not include any symbol characters: {result}"

def test_length_parameter():
    # Test that the length parameter is obeyed
    length = 25
    result = generate_random_string(length)
    assert len(result) == length, f"Expected length {length}, got {len(result)}"
    
    result_with_symbols = generate_random_string(length, include_symbols=True)
    assert len(result_with_symbols) == length, f"Expected length {length}, got {len(result_with_symbols)}"

if __name__ == "__main__":
    pytest.main()