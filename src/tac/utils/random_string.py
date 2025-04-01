import random
import string

def generate_random_string(length=10, include_symbols=False) -> str:
    """
    Generate a random string of specified length.
    
    By default, the generated string contains only alphanumeric characters
    (both upper and lower case letters and digits). If include_symbols is True,
    then punctuation characters are added to the allowed set.
    
    Args:
        length: The length of the string to generate (default is 10).
        include_symbols: Whether to include punctuation symbols in the string.
        
    Returns:
        A random string of the requested length.
    """
    allowed_chars = string.ascii_letters + string.digits
    if include_symbols:
        allowed_chars += string.punctuation
    return ''.join(random.choice(allowed_chars) for _ in range(length))

if __name__ == '__main__':
    # Example usage:
    print("Alphanumeric only:", generate_random_string(15))
    print("Including symbols:", generate_random_string(15, include_symbols=True))