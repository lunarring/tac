import time
import lunar_tools as lt
from tac.core.log_config import setup_logging

logger = setup_logging('tac.cli.voice')


class VoiceUI:
    def __init__(self, prompt_codebase="There is a lot of code here."):
        logger.info("Initializing Voice UI")
        self.temperature = 0.8
        self.prompt_codebase = prompt_codebase
        self.prompt_tac = """You are the TAC Voice Agent, a sassy and sarcastic voice assistant for coding. You are controlling AI coding agents that make software updates for the user. Ask the user what they wanna do! Keep your responses very short and concise."""
        self.prompt_startup = """Ask the user what they want to program"""
        self.instructions = self.generate_instructions()
        logger.debug(f"Generated instructions with codebase prompt: {prompt_codebase}")
        self.rtv = lt.RealTimeVoice(
            instructions=self.instructions,
            temperature=self.temperature
        )

    def generate_instructions(self) -> str:
        """Generate the instructions for the voice UI.
        
        Returns:
            str: The complete instructions including codebase context.
        """
        logger.debug("Generating instructions")
        return self.prompt_tac + "\n" + self.prompt_codebase

    def update_instructions(self):
        """Update the RTV instructions with current instructions."""
        logger.info("Updating voice agent instructions")
        self.instructions = self.generate_instructions()
        self.rtv.update_instructions(self.instructions)

    def start(self):
        """Start the voice UI."""
        logger.info("🎙️ Starting TAC Voice Interface...")
        self.rtv.start()
        self.rtv.inject_message(self.prompt_startup)
        try:
            while True:
                time.sleep(0.1)
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
            self.stop()

    def stop(self):
        """Stop the voice UI."""
        logger.info("Stopping Voice UI")
        self.rtv.stop()

    def inject_message(self, message: str):
        """Inject a message into the voice UI.
        
        Args:
            message: The message to inject.
        """
        logger.debug(f"Injecting message: {message}")
        self.rtv.inject_message(message)


if __name__ == "__main__":
    voice_ui = VoiceUI()
    voice_ui.start()