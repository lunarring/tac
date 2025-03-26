class PromptTransfer:
    def __init__(self):
        self._prompt = ""

    def set_prompt(self, prompt):
        self._prompt = prompt

    def get_prompt(self):
        return self._prompt