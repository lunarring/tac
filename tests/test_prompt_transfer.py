import pytest
from src.tac.communication import PromptTransfer

def test_set_and_get_prompt():
    pt = PromptTransfer()
    test_prompt = "This is a test prompt."
    pt.set_prompt(test_prompt)
    assert pt.get_prompt() == test_prompt

def test_overwrite_prompt():
    pt = PromptTransfer()
    first_prompt = "First prompt."
    second_prompt = "Second prompt."
    pt.set_prompt(first_prompt)
    pt.set_prompt(second_prompt)
    assert pt.get_prompt() == second_prompt

def test_empty_prompt():
    pt = PromptTransfer()
    pt.set_prompt("")
    assert pt.get_prompt() == ""