import asyncio
import os
from aiohttp import web

async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    print("WebSocket connection established")
    async for msg in ws:
        if msg.type == web.WSMsgType.TEXT:
            await ws.send_str("Hello from WebSocket server!")
        elif msg.type == web.WSMsgType.ERROR:
            print(f"WebSocket connection closed with exception {ws.exception()}")
    print("WebSocket connection closed")
    return ws

async def index(request):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(current_dir, "threejs_hello_world.html")
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
    except Exception as e:
        return web.Response(text=f"Error loading HTML: {e}", status=500)
    return web.Response(text=html_content, content_type='text/html')

async def start_server():
    app = web.Application()
    app.router.add_get('/', index)
    app.router.add_get('/ws', websocket_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', 8080)
    print("Starting UI server at http://localhost:8080")
    await site.start()
    # Keep the server running indefinitely.
    while True:
        await asyncio.sleep(3600)

def launch_ui():
    asyncio.run(start_server())