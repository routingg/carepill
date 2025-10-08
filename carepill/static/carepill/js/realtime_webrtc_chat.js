// static/carepill/js/realtime_webrtc_chat.js
// CarePill Realtime Voice UI (logs + audio)

const chatLog = document.getElementById("chatLog");
const statusEl = document.getElementById("rt-status");
const startBtn = document.getElementById("startRtc");
const stopBtn = document.getElementById("stopRtc");

let evtSource = null;

function appendLog(message) {
  const p = document.createElement("p");
  p.textContent = message;
  chatLog.appendChild(p);
  chatLog.scrollTop = chatLog.scrollHeight;
}

startBtn.addEventListener("click", () => {
  appendLog("🎤 CarePill: 실시간 음성 세션을 시작합니다...");
  statusEl.textContent = "연결 중...";
  startBtn.style.display = "none";
  stopBtn.style.display = "inline-block";

  evtSource = new EventSource("/voice-stream/"); // Django view 연결
  evtSource.onmessage = (event) => {
    if (event.data.trim() !== "") {
      appendLog(event.data);
      statusEl.textContent = "활성 중";
    }
  };
  evtSource.onerror = () => {
    appendLog("⚠️ 연결이 종료되었습니다.");
    statusEl.textContent = "연결 끊김";
    evtSource.close();
    startBtn.style.display = "inline-block";
    stopBtn.style.display = "none";
  };
});

stopBtn.addEventListener("click", () => {
  if (evtSource) {
    evtSource.close();
    appendLog("🛑 CarePill 세션이 종료되었습니다.");
    statusEl.textContent = "대기 중";
  }
  startBtn.style.display = "inline-block";
  stopBtn.style.display = "none";
});
