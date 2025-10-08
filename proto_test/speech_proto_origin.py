# speech_realtime_fix_no_audio_block.py
# PyAudio + OpenAI Realtime (server_vad 자동 턴)
# - session.audio 블록 제거 (배포에서 미지원)
# - voice/output_audio_format 만으로 TTS
# - 오디오/텍스트 확실히 출력 + 오디오 수신 감시

import asyncio
import websockets
import pyaudio
import base64
import json
import os
import time

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

API_KEY = os.getenv("OPENAI_API_KEY")

MODEL = "gpt-4o-mini-realtime-preview-2024-12-17"
VOICE = "verse"  # 안 나오면 "alloy"로 바꿔 테스트

RATE = 24000
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1

audio = pyaudio.PyAudio()
input_stream = None
output_stream = None

def b64enc(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")

def b64dec(b64: str) -> bytes:
    return base64.b64decode(b64)

def extract_text_from_completed(msg: dict) -> str:
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
        if texts:
            return " ".join(texts)
    except Exception:
        pass
    return ""

async def run_realtime():
    global input_stream, output_stream, audio

    if not API_KEY:
        print("❌ OPENAI_API_KEY 환경변수가 없습니다.")
        return

    uri = f"wss://api.openai.com/v1/realtime?model={MODEL}"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "OpenAI-Beta": "realtime=v1"
    }

    # 오디오 장치 열기
    input_stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                              input=True, frames_per_buffer=CHUNK)
    output_stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                               output=True, frames_per_buffer=CHUNK)

    print(f"🎧 {MODEL} / voice={VOICE}")
    print("🎙️ 마이크·스피커 준비 완료. 서버 연결 중...")

    async with websockets.connect(uri, additional_headers=headers,
                                  ping_interval=20, ping_timeout=20) as ws:
        print("✅ WebSocket 연결 완료")

        # === 세션 업데이트 ===
        # ⚠️ 'audio' 블록 삭제 (배포에서 미지원)
        session_update = {
            "type": "session.update",
            "session": {
                "modalities": ["audio", "text"],
                "instructions": "You are CarePill, a friendly Korean assistant. Reply in Korean.",
                "voice": VOICE,                     # TTS 음성
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",     # TTS 포맷
                "input_audio_transcription": {"model": "gpt-4o-transcribe"},
                "turn_detection": {"type": "server_vad", "create_response": True, "silence_duration_ms": 500}
            }
        }
        await ws.send(json.dumps(session_update))
        print("🧠 세션 설정 완료 — 서버가 자동으로 턴을 감지합니다.\n")

        async def sender():
            # 오디오 append만 (commit/response.create 금지)
            while True:
                data = input_stream.read(CHUNK, exception_on_overflow=False)
                await ws.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": b64enc(data)
                }))
                await asyncio.sleep(0.02)

        async def receiver():
            text_buf = ""
            user_buf = ""
            audio_chunks = 0
            last_audio_ts = time.time()

            while True:
                raw = await ws.recv()
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue

                t = msg.get("type")

                # 사용자 전사
                if t and t.startswith("input_audio_transcription"):
                    tx = msg.get("transcript") or msg.get("text")
                    if tx and tx.strip():
                        user_buf += tx.strip() + " "
                        print(f"\r🎤 YOU: {user_buf.strip()}", end="", flush=True)

                # 응답 시작
                elif t == "response.created":
                    text_buf = ""
                    print("\n\n🤖 [응답 생성 시작]")

                # 텍스트 델타 (모든 변형)
                elif t in ("response.output_text.delta", "response.text.delta", "response.delta"):
                    delta = msg.get("delta", "")
                    if isinstance(delta, str) and delta:
                        text_buf += delta
                        print(delta, end="", flush=True)

                # 오디오 델타 (모든 변형 + 필드 호환)
                elif t in ("output_audio.delta", "response.output_audio.delta", "response.audio.delta"):
                    audio_b64 = msg.get("audio") or msg.get("delta")
                    if audio_b64:
                        output_stream.write(b64dec(audio_b64))
                        audio_chunks += 1
                        last_audio_ts = time.time()
                        if audio_chunks % 20 == 0:
                            print(f"\n🎵 [오디오 조각 수: {audio_chunks}]")

                # 응답 완료
                elif t in ("response.completed", "response.done", "response.text.done"):
                    final_text = text_buf.strip() or extract_text_from_completed(msg).strip()
                    if final_text:
                        print(f"\n✅ CAREPILL: {final_text}\n")
                    else:
                        print("\n✅ CAREPILL: (음성으로만 응답)\n")
                    user_buf = ""  # 다음 발화 준비
                    # 5초간 오디오가 한 번도 안 왔으면 경고
                    if time.time() - last_audio_ts > 5:
                        print("⚠️ 경고: TTS 오디오가 수신되지 않았습니다. (voice 변경을 시도해보세요. 예: VOICE='alloy')")

                elif t == "error":
                    print(f"\n❗ 서버 오류: {msg}")

        await asyncio.gather(sender(), receiver())

if __name__ == "__main__":
    try:
        asyncio.run(run_realtime())
    except KeyboardInterrupt:
        print("\n🛑 사용자 중단")
    finally:
        try:
            if input_stream:
                if input_stream.is_active(): input_stream.stop_stream()
                input_stream.close()
            if output_stream:
                if output_stream.is_active(): output_stream.stop_stream()
                output_stream.close()
        except Exception:
            pass
        try:
            audio.terminate()
        except Exception:
            pass
        print("🎵 종료")
