// carepill/static/carepill/js/realtime_ws.js
let ws = null;
let pc = null;
let micStream = null;

const startBtn = document.getElementById("startBtn");
const stopBtn  = document.getElementById("stopBtn");
const statusEl = document.getElementById("voiceStatus");
const remoteAudio = document.getElementById("remoteAudio");

function setStatus(msg) {
  statusEl.textContent = msg;
  console.log("[RT]", msg);
}

async function startSession() {
  setStatus("연결 중...");
  ws = new WebSocket("ws://localhost:8765/ws");
  ws.onopen = async () => {
    setStatus("연결 완료. 마이크를 준비 중...");
    micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    pc = new RTCPeerConnection();

    // 원격 오디오 연결
    pc.ontrack = (event) => {
      const [stream] = event.streams;
      remoteAudio.srcObject = stream;
    };
    micStream.getTracks().forEach(t => pc.addTrack(t, micStream));

    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    ws.send(JSON.stringify({ type: "sdp", sdp: offer.sdp }));

    ws.onmessage = async (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === "sdp-answer") {
        await pc.setRemoteDescription({ type: "answer", sdp: msg.sdp });
      } else {
        console.log("[OPENAI]", msg);
      }
    };
    setStatus("🎙️ 대화 시작! 말을 하면 GPT가 응답합니다.");
    startBtn.style.display = "none";
    stopBtn.style.display = "inline-block";
  };

  ws.onclose = () => setStatus("연결 종료됨");
  ws.onerror = (err) => setStatus("에러: " + err.message);
}

async function stopSession() {
  ws && ws.close();
  if (micStream) micStream.getTracks().forEach(t => t.stop());
  if (pc) pc.close();
  setStatus("대기 중");
  startBtn.style.display = "inline-block";
  stopBtn.style.display = "none";
}

startBtn.onclick = startSession;
stopBtn.onclick = stopSession;
