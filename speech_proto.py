import os
import sys
import ssl
import json
import time
import base64
import queue
import asyncio
import websockets
import numpy as np
import sounddevice as sd

# ===== 설정 =====
MODEL = "gpt-4o-realtime-preview"  # 최신 프리뷰 모델
SAMPLE_RATE = 24000                # OpenAI Realtime 기본 권장
CHANNELS = 1
CHUNK_MS = 40                      # 40ms 단위로 전송
CHUNK_SAMPLES = int(SAMPLE_RATE * (CHUNK_MS / 1000.0))
DTYPE = np.int16
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    print("환경변수 OPENAI_API_KEY 가 없습니다. 먼저 설정해 주세요.")
    sys.exit(1)

# ===== 유틸 =====
def pcm16_to_b64(pcm: np.ndarray) -> str:
    """int16 numpy PCM -> base64 str"""
    return base64.b64encode(pcm.tobytes()).decode("ascii")

def b64_to_pcm16(b64: str) -> np.ndarray:
    """base64 str -> int16 numpy PCM"""
    raw = base64.b64decode(b64)
    return np.frombuffer(raw, dtype=DTYPE)

# ===== 녹음 / 재생 =====
class AudioIO:
    def __init__(self, sample_rate=SAMPLE_RATE, channels=CHANNELS):
        self.sample_rate = sample_rate
        self.channels = channels
        self._in_q = queue.Queue()
        self._out_q = queue.Queue()
        self._in_stream = None
        self._out_stream = None

    def _in_callback(self, indata, frames, time_, status):
        if status:
            # print(f"[IN-STATUS] {status}")
            pass
        # mono만 사용
        mono = indata[:, 0].copy() if indata.ndim > 1 else indata.copy()
        self._in_q.put(mono.astype(DTYPE))

    def _out_callback(self, outdata, frames, time_, status):
        if status:
            # print(f"[OUT-STATUS] {status}")
            pass
        try:
            chunk = self._out_q.get_nowait()
        except queue.Empty:
            chunk = np.zeros(frames, dtype=DTYPE)
        if len(chunk) < frames:
            padded = np.zeros(frames, dtype=DTYPE)
            padded[:len(chunk)] = chunk
            chunk = padded
        outdata[:, 0] = chunk  # mono

    def start(self):
        self._in_stream = sd.InputStream(
            channels=1,
            samplerate=self.sample_rate,
            dtype=DTYPE,
            callback=self._in_callback,
            blocksize=CHUNK_SAMPLES,
        )
        self._out_stream = sd.OutputStream(
            channels=1,
            samplerate=self.sample_rate,
            dtype=DTYPE,
            callback=self._out_callback,
            blocksize=CHUNK_SAMPLES,
        )
        self._in_stream.start()
        self._out_stream.start()

    def stop(self):
        try:
            if self._in_stream: self._in_stream.stop(); self._in_stream.close()
            if self._out_stream: self._out_stream.stop(); self._out_stream.close()
        except Exception:
            pass

    def read_chunk(self, block=True, timeout=None) -> np.ndarray | None:
        try:
            return self._in_q.get(block=block, timeout=timeout)
        except queue.Empty:
            return None

    def play_chunk(self, pcm: np.ndarray):
        self._out_q.put(pcm)

# ===== Realtime WebSocket 세션 =====
async def run_session():
    uri = f"wss://api.openai.com/v1/realtime?model={MODEL}"
    headers = [
        ("Authorization", f"Bearer {OPENAI_API_KEY}"),
        ("OpenAI-Beta", "realtime=v1"),
    ]
    # Windows용 기본 SSL 컨텍스트
    ssl_context = ssl.create_default_context()

    audio = AudioIO()
    audio.start()
    print("🎤 준비 완료! Enter를 누르면 3초간 녹음 → 전송 → 음성응답 재생합니다. (q + Enter 로 종료)")

    async with websockets.connect(uri, additional_headers=headers, ssl=ssl_context, ping_interval=20, ping_timeout=20) as ws:

        async def receiver():
            """서버에서 오는 이벤트 수신: output_audio.delta 를 재생 큐에 밀어넣음."""
            try:
                async for raw in ws:
                    msg = json.loads(raw)
                    t = msg.get("type")
                    if t == "response.created":
                        print("🤖 응답 생성 시작")
                    elif t == "response.delta":
                        # 텍스트 토큰 스트림(있을 수도)
                        delta = msg.get("delta")
                        if isinstance(delta, str) and delta:
                            print(delta, end="", flush=True)
                    elif t == "response.output_text.delta":
                        # 새 포맷일 경우
                        delta = msg.get("delta", "")
                        if delta:
                            print(delta, end="", flush=True)
                    elif t == "response.completed":
                        print("\n✅ 응답 완료")
                    elif t == "output_audio.delta":
                        # 오디오 조각(base64 PCM16)
                        b64 = msg.get("audio")
                        if b64:
                            pcm = b64_to_pcm16(b64)
                            audio.play_chunk(pcm)
                    elif t == "error":
                        print(f"\n[SERVER ERROR] {msg}")
                    # else:
                    #     print("[DBG EVT]", t, msg)
            except websockets.ConnectionClosed as e:
                print(f"[WS CLOSED] {e}")

        recv_task = asyncio.create_task(receiver())

        try:
            while True:
                user = input("> Enter = 말하기 / q = 종료: ").strip().lower()
                if user == "q":
                    break

                # 1) 3초 녹음
                print("🎙 3초 녹음 중...")
                frames = []
                start_t = time.time()
                while time.time() - start_t < 3.0:
                    chunk = audio.read_chunk(timeout=0.1)
                    if chunk is not None:
                        frames.append(chunk)
                if not frames:
                    print("마이크 입력이 없습니다.")
                    continue
                pcm = np.concatenate(frames)

                # 2) 오디오 버퍼 append
                await ws.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": pcm16_to_b64(pcm),
                }))
                # 3) commit
                await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))

                # 4) 응답 생성 트리거 (음성 출력 포함)
                await ws.send(json.dumps({
                    "type": "response.create",
                    "response": {
                        "modalities": ["audio", "text"],
                        "instructions": "You are CarePill, a friendly Korean medication assistant. Reply in Korean.",
                        "audio": {"voice": "alloy", "format": "pcm16", "sample_rate": SAMPLE_RATE},
                    }
                }))

                print("📨 전송 완료. 응답 대기 중...")
                # receiver() 태스크가 오디오를 재생해줌

        finally:
            recv_task.cancel()
            audio.stop()

if __name__ == "__main__":
    try:
        asyncio.run(run_session())
    except KeyboardInterrupt:
        print("\n종료합니다.")
