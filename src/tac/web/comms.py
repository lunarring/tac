class Web2PythonTransfer:
    def __init__(self):
        self._payload = None

    def set_payload(self, payload):
        self._payload = payload

    def get_payload(self):
        return self._payload