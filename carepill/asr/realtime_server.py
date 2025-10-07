# carepill/asr/realtime_server.py
import os
import json
import asyncio
import websockets
import requests
from dotenv import load_dotenv

load_dotenv()
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

# 클라이언트(Web) <-> Django(WebSocket) <-> OpenAI Realtime WebSocket
# 중계 서버

async def relay(websocket, path):
    print("[SERVER] New client connected")

    # OpenAI Realtime API WebSocket 열기
    async with websockets.connect(
        "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview",
        extra_headers={
            "Authorization": f"Bearer {OPENAI_KEY}",
            "OpenAI-Beta": "realtime=v1",
        },
    ) as openai_ws:

        async def from_client():
            async for message in websocket:
                try:
                    data = json.loads(message)
                except:
                    data = message
                await openai_ws.send(json.dumps(data))

        async def from_openai():
            async for message in openai_ws:
                await websocket.send(message)

        # 클라이언트 ↔ OpenAI 양방향 relay
        await asyncio.gather(from_client(), from_openai())

    print("[SERVER] Client disconnected")


def start_realtime_server():
    import uvicorn
    from fastapi import FastAPI
    from fastapi.websockets import WebSocket
    app = FastAPI()

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await ws.accept()
        async with websockets.connect(
            "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview",
            extra_headers={
                "Authorization": f"Bearer {OPENAI_KEY}",
                "OpenAI-Beta": "realtime=v1",
            },
        ) as openai_ws:
            async def client_to_openai():
                async for msg in ws.iter_text():
                    await openai_ws.send(msg)
            async def openai_to_client():
                async for msg in openai_ws:
                    await ws.send_text(msg)
            await asyncio.gather(client_to_openai(), openai_to_client())

    print("Realtime WS running at ws://0.0.0.0:8765/ws")
    uvicorn.run(app, host="0.0.0.0", port=8765)

if __name__ == "__main__":
    start_realtime_server()
