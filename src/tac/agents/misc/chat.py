from tac.core.llm import Message, LLMClient

class ChatAgent:
    def __init__(self, system_prompt: str = "You are a helpful assistant."):
        """
        Initialize the ChatAgent with an optional system prompt.
        The conversation state is initiated with a system message.
        """
        self.conversation = []
        self.conversation.append(Message(role="system", content=system_prompt))
        self.llm_client = LLMClient(llm_type="weak")
    
    def process_message(self, user_message: str) -> str:
        """
        Processes a new user message by appending it to the conversation,
        generating an assistant response using the LLM client,
        appending the assistant's response to the conversation, and then returning it.
        """
        # Append the new user message.
        self.conversation.append(Message(role="user", content=user_message))
        # Generate response using LLM
        response = self.llm_client.chat_completion(self.conversation)
        # Append the assistant's response to the conversation.
        self.conversation.append(Message(role="assistant", content=response))
        return response
       
# For manual testing if needed.
if __name__ == "__main__":
    agent = ChatAgent(system_prompt="You are a helpful assistant.")
    print("Chat started. Type 'exit' to end the conversation.")
    while True:
        user_input = input("\nYou: ")
        if user_input.lower() in ["exit", "quit", "bye"]:
            print("Conversation ended.")
            break
        response = agent.process_message(user_input)
        print(f"\nAssistant: {response}")