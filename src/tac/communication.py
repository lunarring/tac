class PromptTransfer:
    def __init__(self):
        self._payload = None

    def set_prompt(self, prompt):
        self._payload = prompt

    def get_prompt(self):
        return self._payload