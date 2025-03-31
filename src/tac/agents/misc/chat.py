from tac.core.llm import Message

class ChatAgent:
    def __init__(self, system_prompt: str = "You are a helpful assistant."):
        """
        Initialize the ChatAgent with an optional system prompt.
        The conversation state is initiated with a system message.
        """
        self.conversation = []
        self.conversation.append(Message(role="system", content=system_prompt))
    
    def process_message(self, user_message: str) -> str:
        """
        Processes a new user message by appending it to the conversation,
        generating an assistant response by concatenating all system and user messages,
        appending the assistant's response to the conversation, and then returning it.
        """
        # Append the new user message.
        self.conversation.append(Message(role="user", content=user_message))
        # Select only system and user messages as relevant for generating response.
        relevant_contents = [msg.content for msg in self.conversation if msg.role in ("system", "user")]
        response = " ".join(relevant_contents)
        # Append the assistant's response to the conversation.
        self.conversation.append(Message(role="assistant", content=response))
        return response
       
# For manual testing if needed.
if __name__ == "__main__":
    agent = ChatAgent(system_prompt="System")
    print("Assistant response:", agent.process_message("Hello"))