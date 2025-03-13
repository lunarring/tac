import pytest
from tac.core.llm import LLMClient

# Use an instance of LLMClient without calling __init__
# because _clean_code_fences does not depend on any instance attributes.
client = object.__new__(LLMClient)

def test_triple_backticks_with_language():
    input_text = "```python\nprint('hello world')\n```"
    expected_output = "print('hello world')"
    result = client._clean_code_fences(input_text)
    assert result == expected_output

def test_triple_backticks_without_language():
    input_text = "```\nhello world\n```"
    expected_output = "hello world"
    result = client._clean_code_fences(input_text)
    assert result == expected_output

def test_inline_code_fence():
    # The function does not remove inline backticks if not wrapped by triple backticks.
    input_text = "This is `inline code` sample."
    expected_output = "This is `inline code` sample."
    result = client._clean_code_fences(input_text)
    assert result == expected_output

def test_no_code_fences():
    input_text = "This is a plain text without markdown formatting."
    expected_output = "This is a plain text without markdown formatting."
    result = client._clean_code_fences(input_text)
    assert result == expected_output