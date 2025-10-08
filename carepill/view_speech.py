# carepill/view_speech.py
# Django SSE + OpenAI Realtime + (서버측) PyAudio 마이크/스피커 스트리밍
import asyncio
import json
import os
import base64
import websockets
import pyaudio
from django.http import StreamingHttpResponse
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")

MODEL = "gpt-4o-mini-realtime-preview-2024-12-17"
VOICE = "verse"

RATE = 24000
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1

def b64enc(b: bytes) -> str:
    return base64.b64encode(b).decode("utf-8")

def b64dec(s: str) -> bytes:
    return base64.b64decode(s)

def extract_text_from_completed(msg: dict) -> str:
    """
    response.completed 메시지에서 최종 텍스트를 안전하게 뽑아냄.
    구조: msg["response"]["output"][i]["text"] 또는 ["content"][j]["text"]
    """
    try:
        resp = msg.get("response") or {}
        output = resp.get("output") or []
        texts = []
        for item in output:
            if isinstance(item, dict):
                t1 = item.get("text")
                if isinstance(t1, str) and t1.strip():
                    texts.append(t1.strip())
                content = item.get("content")
                if isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict):
                            t2 = c.get("text") or c.get("transcript")
                            if isinstance(t2, str) and t2.strip():
                                texts.append(t2.strip())
        return " ".join(texts).strip()
    except Exception:
        return ""

async def openai_realtime_stream():
    if not API_KEY:
        yield "data: OPENAI_API_KEY not set\n\n"
        return

    # 오디오 장치
    pa = pyaudio.PyAudio()
    mic = spk = None
    try:
        mic = pa.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                      input=True, frames_per_buffer=CHUNK)
        spk = pa.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                      output=True, frames_per_buffer=CHUNK)
    except Exception as e:
        yield f"data: Audio device open failed: {e}\n\n"
        return

    uri = f"wss://api.openai.com/v1/realtime?model={MODEL}"
    headers = {"Authorization": f"Bearer {API_KEY}", "OpenAI-Beta": "realtime=v1"}

    yield "data: Connecting to CarePill Realtime Server...\n\n"

    async with websockets.connect(uri, additional_headers=headers,
                                  ping_interval=30, ping_timeout=60) as ws:
        yield "data: Connected to OpenAI Realtime API\n\n"

        # 세션 설정: 텍스트도 항상 함께 반환하도록 요청
        session_update = {
            "type": "session.update",
            "session": {
                "modalities": ["audio", "text"],
                "instructions": (
                    "You are 'CarePill', a voice-based medication assistant for visually impaired users. "
                    "Speak Korean with clear, precise pronunciation, like a professional news announcer. "
                    "Provide guidance on medication usage, dosage, timing, and potential drug interactions. "
                    "Offer emotional support and speak warmly, like a trusted friend. "
                    "Always return a concise text version of your spoken reply as well."
                ),
                "voice": VOICE,
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {"model": "gpt-4o-transcribe"},
                "turn_detection": {"type": "server_vad", "create_response": True, "silence_duration_ms": 500},
            }
        }
        await ws.send(json.dumps(session_update))
        yield "data: Session initialized.\n\n"
        yield "data: Mic streaming started...\n\n"

        # 마이크 송신 태스크
        async def sender():
            try:
                while True:
                    data = mic.read(CHUNK, exception_on_overflow=False)
                    await ws.send(json.dumps({
                        "type": "input_audio_buffer.append",
                        "audio": b64enc(data)
                    }))
                    await asyncio.sleep(0.03)
            except asyncio.CancelledError:
                pass

        sender_task = asyncio.create_task(sender())

        # 상태 변수
        text_buf = ""           # 텍스트 델타 누적
        audio_chunks = 0

        try:
            while True:
                raw = await ws.recv()
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue

                t = msg.get("type")

                if t == "input_audio_buffer.speech_started":
                    yield "data: Listening...\n\n"
                elif t == "input_audio_buffer.speech_stopped":
                    yield "data: Processing...\n\n"

                elif t == "conversation.item.input_audio_transcription.completed":
                    tx = msg.get("transcript")
                    if tx and tx.strip():
                        yield f"data: YOU: {tx.strip()}\n\n"

                elif t == "response.created":
                    text_buf = ""
                    yield "data: Generating response...\n\n"

                # 텍스트 델타: 가능한 타입을 폭넓게 처리
                elif t in ("response.output_text.delta", "response.text.delta", "response.delta"):
                    delta = msg.get("delta") or ""
                    if isinstance(delta, str) and delta:
                        text_buf += delta
                        # 필요시 실시간 델타도 표출하려면 주석 해제
                        # yield f"data: {delta}\n\n"

                # 오디오 델타
                elif t in ("output_audio.delta", "response.output_audio.delta", "response.audio.delta"):
                    audio_b64 = msg.get("audio") or msg.get("delta")
                    if audio_b64:
                        spk.write(b64dec(audio_b64))
                        audio_chunks += 1
                        if audio_chunks % 30 == 0:
                            yield "data: [playing...]\n\n"

                elif t in ("response.completed", "response.done", "response.text.done"):
                    # 최종 텍스트 확정
                    final_text = text_buf.strip() or extract_text_from_completed(msg).strip()
                    if final_text:
                        yield f"data: CAREPILL: {final_text}\n\n"
                    else:
                        yield "data: CAREPILL: (audio only)\n\n"

                elif t == "error":
                    yield f"data: ERROR: {msg}\n\n"

        except websockets.ConnectionClosed:
            yield "data: Connection closed.\n\n"
        finally:
            sender_task.cancel()
            try:
                await sender_task
            except Exception:
                pass

    # 자원 정리
    try:
        if mic:
            if mic.is_active(): mic.stop_stream()
            mic.close()
        if spk:
            if spk.is_active(): spk.stop_stream()
            spk.close()
    except Exception:
        pass
    try:
        pa.terminate()
    except Exception:
        pass

def voice_stream_view(request):
    """Django가 async generator를 동기 이터레이터로 소비하도록 래핑"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    agen = openai_realtime_stream()

    def sync_iter():
        try:
            while True:
                chunk = loop.run_until_complete(agen.__anext__())
                yield chunk
        except StopAsyncIteration:
            pass
        finally:
            loop.close()

    resp = StreamingHttpResponse(sync_iter(), content_type="text/event-stream")
    resp["Cache-Control"] = "no-cache"
    resp["X-Accel-Buffering"] = "no"  # nginx 앞단 버퍼링 우회용(있다면)
    return resp
