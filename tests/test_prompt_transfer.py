import pytest
from tac.web.comms import Web2PythonTransfer

def test_set_and_get_prompt():
    pt = Web2PythonTransfer()
    test_prompt = "This is a test prompt."
    pt.set_payload(test_prompt)
    assert pt.get_payload() == test_prompt

def test_overwrite_prompt():
    pt = Web2PythonTransfer()
    first_prompt = "First prompt."
    second_prompt = "Second prompt."
    pt.set_payload(first_prompt)
    pt.set_payload(second_prompt)
    assert pt.get_payload() == second_prompt

def test_empty_prompt():
    pt = Web2PythonTransfer()
    pt.set_payload("")
    assert pt.get_payload() == ""