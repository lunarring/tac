import asyncio
import threading
import time
import websockets
from tac.communication import PromptTransfer

class UIPromptInjector:
    def __init__(self):
        self._prompt_transfer = PromptTransfer()
        self._server = None
        self._thread = None

    async def _handler(self, websocket, path):
        try:
            message = await websocket.recv()
            self._prompt_transfer.set_prompt(message)
        except Exception as e:
            print(f"Error in UIPromptInjector handler: {e}")

    async def _start_server(self):
        self._server = await websockets.serve(self._handler, "localhost", 8767)
        await self._server.wait_closed()

    def start(self):
        def run_loop():
            asyncio.run(self._start_server())
        self._thread = threading.Thread(target=run_loop, daemon=True)
        self._thread.start()

    def wait_until_prompt(self, timeout=30):
        start_time = time.time()
        while time.time() - start_time < timeout:
            prompt = self.get_prompt()
            if prompt is not None:
                return prompt
            time.sleep(0.5)
        return None

    def get_prompt(self):
        return self._prompt_transfer.get_prompt()