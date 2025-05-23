from tac.core.llm import Message, LLMClient

class ChatAgent:
    def __init__(self, system_prompt: str = "You are a helpful assistant."):
        """
        Initialize the ChatAgent with an optional system prompt.
        The conversation state is initiated with a system message.
        """
        self.conversation = []
        self.conversation.append(Message(role="system", content=system_prompt))
        self.llm_client = LLMClient(component="chat")
    
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
    
    def get_messages(self):
        """
        Returns the full conversation history.
        """
        return self.conversation
    
    def add_message(self, role: str, content: str):
        """
        Adds a message to the conversation history without generating a response.
        
        Args:
            role (str): The role of the message sender ('user', 'assistant', or 'system')
            content (str): The content of the message
        """
        self.conversation.append(Message(role=role, content=content))
    
    def generate_task_instructions_llm(self) -> str:
        """
        Summarizes the conversation history into a clear, concise set of task instructions.
        
        Returns:
            str: Compressed conversation as task instructions
        """
        # Skip if there's not enough conversation to summarize
        if len(self.conversation) <= 2:  # Only system prompt and maybe one exchange
            return "No substantial conversation to summarize."
        
        # Use a native_agent LLM for summarization
        summarizer = LLMClient(component="native_agent")
        
        # Format the conversation for the summary prompt
        conversation_text = "\n".join([f"{msg.role}: {msg.content}" for msg in self.conversation])
        
        # Prepare the prompt for summarization
        system_prompt = "You are a helpful assistant that can summarize conversations into clear, concise instructions."
        user_prompt = "Please compress the following conversation into a clear, concise instruction set that captures the core requirements. Especially take into account what the user has been saying and what the assistant said is less important. Also the last messages are especially important. The summary should be specific, actionable, and focused on what needs to be implemented:\n\n" + conversation_text
        
        # Create messages for the LLM
        summary_messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_prompt)
        ]
        
        # Get the summary from the LLM
        summary = summarizer.chat_completion(summary_messages)
        return summary    
    
    def generate_task_instructions(self) -> str:
        """
        Summarizes the conversation history into a clear, concise set of task instructions.
        
        Returns:
            str: Compressed conversation as task instructions
        """
        # Use a native_agent LLM for summarization
        # Format the conversation for the summary prompt
        conversation_text = "\n".join([f"{msg.role}: {msg.content}" for msg in self.conversation])
        
        task_instructions = f"""We have the following conversation between a user and an AI assistant: 
{conversation_text}

Your task is now to find out what the user wants and rephrase it given the codebase. Pay special attention to what the user says, particularly towards the end. Ignore the AI messages, they are here just for context."""
        
        # Get the summary from the LLM
        return task_instructions
        
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