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
    # Create a chat LLM client instance
    client = LLMClient(component="chat")
    messages = [
        Message(role="system", content="You are a helpful assistant."),
        Message(role="user", content=message)
    ]
    response = client.chat_completion(messages)
    return response