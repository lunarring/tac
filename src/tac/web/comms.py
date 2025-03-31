"""
This module contains functions for communication between the Python backend
and the web frontend.
"""

class Web2PythonTransfer:
    def __init__(self):
        self._payload = None

    def set_payload(self, payload):
        self._payload = payload

    def get_payload(self):
        return self._payload

def process_chat_message(message):
    """
    Process a chat message by calling the LLM functionality to generate a response.

    Args:
        message (str): The user's message.

    Returns:
        str: The AI-generated response.
    """
    from tac.core.llm import LLMClient, Message
    # Create a weak LLM client instance
    client = LLMClient(llm_type="weak")
    messages = [
        Message(role="system", content="You are a helpful assistant."),
        Message(role="user", content=message)
    ]
    response = client.chat_completion(messages)
    return response

def create_amplitude_message(amplitude):
    """
    Create a JSON formatted amplitude message to be sent to the frontend.
    Args:
        amplitude (float): The amplitude value.
    Returns:
        str: A JSON string with the amplitude data.
    """
    import json
    return json.dumps({"type": "amplitude", "amplitude": amplitude})

def set_audio_recorder_amplitude_callback(ws, audio_recorder):
    """
    Sets the amplitude callback of the given AudioRecorder so that each computed
    amplitude value is forwarded to the browser via the provided WebSocket connection.
    
    Args:
        ws: A WebSocket connection object with a send() method.
        audio_recorder: An instance of AudioRecorder.
    """
    def callback(amplitude):
        # Forward the amplitude value using the create_amplitude_message helper.
        message = create_amplitude_message(amplitude)
        ws.send(message)
    audio_recorder.set_amplitude_callback(callback)
    