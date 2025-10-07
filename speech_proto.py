# speech_proto.py
DEBUG_EVENTS = True


import os
import ssl
import json
import time
import base64
import asyncio
import queue
import numpy as np
import sounddevice as sd
import websockets

# ===== 설정 =====
MODEL = "gpt-4o-realtime-preview"
SAMPLE_RATE = 24000
DTYPE = np.int16
CHUNK_MS = 40
CHUNK_SAMPLES = int(SAMPLE_RATE * (CHUNK_MS / 1000.0))
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise SystemExit("환경변수 OPENAI_API_KEY 가 없습니다.")

# 침묵 감지(간단 RMS)
SILENCE_MS = 550            # 이만큼 조용하면 commit (500~800 사이 조정 권장)
VOICE_RMS_THRESHOLD = 500   # 200~2000 범위에서 환경에 맞게 조절

# 로깅/디버깅
LOG_TO_FILE = False
DEBUG_EVENTS = False
LOG_PATH = "transcript.log"

# ===== 유틸 =====
def pcm16_to_b64(pcm: np.ndarray) -> str:
    return base64.b64encode(pcm.tobytes()).decode("ascii")

def b64_to_pcm16(b64: str) -> np.ndarray:
    return np.frombuffer(base64.b64decode(b64), dtype=DTYPE)

def rms_level(chunk: np.ndarray) -> float:
    if chunk is None or len(chunk) == 0:
        return 0.0
    return float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))

def log_append(line: str):
    if not LOG_TO_FILE:
        return
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line.rstrip() + "\n")
    except Exception:
        pass

# ===== 녹음 / 재생 =====
class AudioIO:
    def __init__(self, sample_rate=SAMPLE_RATE):
        self.sample_rate = sample_rate
        self.in_q: "queue.Queue[np.ndarray]" = queue.Queue()
        self.out_q: "queue.Queue[np.ndarray]" = queue.Queue()
        self._in_stream = None
        self._out_stream = None

    def _in_callback(self, indata, frames, time_, status):
        if status:
            pass
        mono = indata[:, 0].copy() if indata.ndim > 1 else indata.copy()
        self.in_q.put(mono.astype(DTYPE))

    def _out_callback(self, outdata, frames, time_, status):
        if status:
            pass
        try:
            chunk = self.out_q.get_nowait()
        except queue.Empty:
            chunk = np.zeros(frames, dtype=DTYPE)
        if len(chunk) < frames:
            padded = np.zeros(frames, dtype=DTYPE)
            padded[:len(chunk)] = chunk
            chunk = padded
        outdata[:, 0] = chunk

    def start(self):
        # 문제 생기면 blocksize=None로 바꿔서 테스트
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
        for s in (self._in_stream, self._out_stream):
            if s:
                try:
                    s.stop()
                    s.close()
                except Exception:
                    pass

    def read_chunk(self, timeout=0.2) -> np.ndarray | None:
        try:
            return self.in_q.get(timeout=timeout)
        except queue.Empty:
            return None

    def play_chunk(self, pcm: np.ndarray):
        self.out_q.put(pcm)

# ===== WebSocket 세션 =====
async def run_session():
    uri = f"wss://api.openai.com/v1/realtime?model={MODEL}"
    headers = [
        ("Authorization", f"Bearer {OPENAI_API_KEY}"),
        ("OpenAI-Beta", "realtime=v1"),
    ]
    ssl_context = ssl.create_default_context()

    audio = AudioIO()
    audio.start()
    print("실시간 대화 시작: 말하면 서버가 VAD로 턴을 감지합니다. (Ctrl+C 종료)")

    async with websockets.connect(
        uri, additional_headers=headers, ssl=ssl_context,
        ping_interval=20, ping_timeout=20
    ) as ws:

        # ---- 세션 설정: 서버 VAD 사용, 전사 ON, 포맷/보이스 명시 ----
        await ws.send(json.dumps({
            "type": "session.update",
            "session": {
                "modalities": ["audio", "text"],
                "instructions": "You are CarePill, a friendly Korean medication assistant. Reply in concise Korean.",
                "voice": "alloy",
                "input_audio_format": {"type": "pcm16", "sample_rate": SAMPLE_RATE},
                "output_audio_format": {"type": "pcm16", "sample_rate": SAMPLE_RATE},
                "turn_detection": { "type": "server_vad" },  # 서버가 턴을 만들고 응답 생성
                "input_audio_transcription": { "model": "gpt-4o-transcribe" }
            }
        }))

        # ----- 상태/버퍼 -----
        user_text_buf = ""      # 사용자 전사 누적
        model_text_buf = ""     # 모델 텍스트 누적

        # ----- 출력 헬퍼 -----
        def flush_user():
            nonlocal user_text_buf
            text = user_text_buf.strip()
            if text:
                line = f"YOU: {text}"
                print("\n" + line)
                log_append(line)
            user_text_buf = ""

        def flush_model():
            nonlocal model_text_buf
            text = model_text_buf.strip()
            if text:
                line = f"CAREPILL: {text}"
                print(line + "\n")
                log_append(line)
            model_text_buf = ""

        # ----- 전사 추출(여러 포맷 대응) -----
        def extract_transcript_fields(msg: dict) -> str:
            # 1) 평평한 키
            for k in ("transcript", "text"):
                v = msg.get(k)
                if isinstance(v, str) and v.strip():
                    return v

            # 2) nested transcription object
            trans = msg.get("transcription")
            if isinstance(trans, dict):
                for k in ("text", "transcript"):
                    v = trans.get(k)
                    if isinstance(v, str) and v.strip():
                        return v

            # 3) conversation.item.created 구조 (item.content[*].text/transcript)
            item = msg.get("item")
            if isinstance(item, dict):
                content = item.get("content") or []
                if isinstance(content, list):
                    for c in content:
                        if not isinstance(c, dict):
                            continue
                        for k in ("text", "transcript"):
                            v = c.get(k)
                            if isinstance(v, str) and v.strip():
                                return v
            return ""

        # ----- 수신 루프 -----
        async def receiver():
            nonlocal user_text_buf, model_text_buf
            try:
                async for raw in ws:
                    msg = json.loads(raw)
                    t = msg.get("type")

                    if t == "session.updated":
                        print("[세션 업데이트 완료]")

                    # 서버가 응답을 만들었을 때
                    elif t == "response.created":
                        model_text_buf = ""
                        print("[응답 시작]")

                    # 모델 텍스트 스트림
                    elif t == "response.text.delta":
                        delta = msg.get("delta") or ""
                        if delta:
                            model_text_buf += delta
                    elif t == "response.text.done":
                        flush_model()

                    # 일부 배포 호환
                    elif t == "response.output_text.delta":
                        delta = msg.get("delta") or ""
                        if delta:
                            model_text_buf += delta

                    # 모델 오디오 스트림
                    elif t == "response.audio.delta":
                        b64 = msg.get("audio")
                        if b64:
                            pcm = b64_to_pcm16(b64)
                            audio.play_chunk(pcm)

                    # 사용자 전사 이벤트(가능한 모든 신호 처리)
                    elif t in (
                        "conversation.item.audio_transcription.delta",
                        "conversation.item.audio_transcription.completed",
                        "conversation.item.input_audio_transcription.delta",
                        "conversation.item.input_audio_transcription.completed",
                        "input_audio_transcription.delta",
                        "input_audio_transcription.completed",
                        "conversation.item.created",  # user input item 생성
                    ):
                        transcript = extract_transcript_fields(msg)
                        if transcript:
                            user_text_buf += transcript
                        # 경계 이벤트에서 flush
                        if t.endswith(".completed") or t == "conversation.item.created":
                            flush_user()

                    elif t == "response.done":
                        flush_model()

                    elif t == "error":
                        print(f"[SERVER ERROR] {msg}")

                    else:
                        if DEBUG_EVENTS:
                            print(f"[DBG] Unhandled event type: {t} :: keys={list(msg.keys())}")

            except websockets.ConnectionClosed as e:
                print(f"[WS CLOSED] {e}")

        # ----- 송신 루프: append 하다가 '침묵'이면 commit만 보냄 -----
        async def sender():
            last_voice_ts = time.time()
            had_voice_since_last_commit = False

            while True:
                chunk = await asyncio.to_thread(audio.read_chunk, 0.2)
                now = time.time()

                if chunk is not None and len(chunk) > 0:
                    # 마이크 오디오 append
                    await ws.send(json.dumps({
                        "type": "input_audio_buffer.append",
                        "audio": pcm16_to_b64(chunk)
                    }))

                    # 간단 RMS로 발화 감지
                    if rms_level(chunk) > VOICE_RMS_THRESHOLD:
                        last_voice_ts = now
                        had_voice_since_last_commit = True

                # 발화가 있었고, 일정 시간 침묵이 지속되면 commit(턴 종료)
                if had_voice_since_last_commit and (now - last_voice_ts) * 1000 >= SILENCE_MS:
                    await ws.send(json.dumps({ "type": "input_audio_buffer.commit" }))
                    had_voice_since_last_commit = False
                    # 서버 VAD가 이미 켜져 있어도 commit은 턴 경계 힌트로 안전

        rx_task = asyncio.create_task(receiver())
        tx_task = asyncio.create_task(sender())

        try:
            await asyncio.gather(rx_task, tx_task)
        finally:
            for t in (rx_task, tx_task):
                t.cancel()
            audio.stop()

if __name__ == "__main__":
    try:
        asyncio.run(run_session())
    except KeyboardInterrupt:
        print("종료")
