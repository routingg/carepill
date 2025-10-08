// == carepill 대화 내용이 자꾸 위로만 찍히는 에러가 있는 코드 ==

(function () {
  // ===== DOM =====
  const $ = (id) => document.getElementById(id);
  const elStart = $("startRtc");
  const elStop = $("stopRtc");
  const elStatus = $("rt-status");
  const elAudio = $("remoteAudio");
  const elLog = $("chatLog");

  // ===== State =====
  let pc = null, dc = null, mic = null;
  let audioCtx = null, analyser = null, rafId = null;
  let speaking = false, vadStart = 0, lastCancelAt = 0;

  // 진행 중 출력 줄(한 턴당 한 줄만 업데이트)
  let userLine = null, userBuf = "";
  let botLine = null,  botBuf  = "";

  // ===== Log helpers (모두 #chatLog 안에 출력) =====
  function appendLine(prefix, text, cssRole) {
    const div = document.createElement("div");
    if (cssRole) div.dataset.role = cssRole; // 필요 시 CSS 후처리용
    div.textContent = (prefix ? prefix + " " : "") + (text ?? "");
    elLog.appendChild(div);
    elLog.scrollTop = elLog.scrollHeight;
    return div;
  }
  function setLine(line, prefix, text) {
    if (!line) return;
    line.textContent = (prefix ? prefix + " " : "") + (text ?? "");
    elLog.scrollTop = elLog.scrollHeight;
  }
  const logSys = (msg) => appendLine("SYS:", msg, "sys");
  const logEvt = (msg) => appendLine("EVT:", msg, "evt"); // 필요 시 주석 처리 가능

  // ===== UI =====
  function ui(state){
    // state: idle | connecting | connected | stopped
    const map = { idle:"대기 중", connecting:"연결 중…", connected:"연결됨 (바지-인 가능)", stopped:"종료됨" };
    elStatus.textContent = map[state] || state;
    elStart.style.display = (state === "idle" || state === "stopped") ? "" : "none";
    elStop.style.display  = (state === "connected" || state === "connecting") ? "" : "none";
  }

  // ===== Ephemeral =====
  async function getEphemeral(){
    const r = await fetch("/api/realtime/session/", { method:"GET" });
    let j; try { j = await r.json(); } catch { throw new Error("ephemeral non-json"); }
    if (!j || !j.value) throw new Error("invalid ephemeral response");
    return j.value;
  }

  // ===== User/Bot line updaters =====
  function userDelta(chunk) {
    if (!userLine) userLine = appendLine("user:", "", "user");
    if (chunk) userBuf = chunk; // 전사는 보통 문장 단위로 덮어씀
    setLine(userLine, "user:", userBuf || "(speaking…)");
  }
  function userFinal(text) {
    if (!userLine) userLine = appendLine("user:", "", "user");
    if (text) userBuf = text;
    setLine(userLine, "user:", userBuf);
    userLine = null; userBuf = "";
  }
  function botDelta(chunk) {
    if (!botLine) botLine = appendLine("carepill:", "", "assistant");
    if (chunk) botBuf += chunk;          // 어시스턴트는 델타를 누적
    setLine(botLine, "carepill:", botBuf);
  }
  function botFinal(text) {
    if (!botLine) botLine = appendLine("carepill:", "", "assistant");
    if (text && !botBuf) botBuf = text;  // 델타 없이 한 번에 올 수도 있음
    setLine(botLine, "carepill:", botBuf);
    botLine = null; botBuf = "";
  }

  // ===== Start/Stop WebRTC =====
  async function startRtc(){
    if (pc) return;
    ui("connecting");
    logSys("Starting WebRTC…");

    const EPHEMERAL_KEY = await getEphemeral().catch(e => { throw new Error("ephemeral fetch failed: " + e.message); });
    logSys("Ephemeral OK");

    pc = new RTCPeerConnection();

    // Remote audio
    const remoteStream = new MediaStream();
    pc.ontrack = (e) => {
      e.streams[0].getAudioTracks().forEach(t => remoteStream.addTrack(t));
      elAudio.srcObject = remoteStream;
    };
    pc.onconnectionstatechange = () => {
      logEvt("pc.state: " + pc.connectionState);
      if (pc.connectionState === "connected") ui("connected");
      if (["disconnected", "failed", "closed"].includes(pc.connectionState)) ui("stopped");
    };

    // DataChannel
    dc = pc.createDataChannel("oai-events");
    dc.onopen    = () => logSys("DataChannel open");
    dc.onclose   = () => logEvt("DataChannel close");
    dc.onerror   = (e) => logEvt("DataChannel error: " + (e.message || e));
    dc.onmessage = (e) => handleDCMessage(e.data);

    // Microphone
    mic = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation:true, noiseSuppression:true, autoGainControl:true }
    });
    mic.getTracks().forEach(t => pc.addTrack(t, mic));

    // SDP offer → (server proxy) → answer
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);

    const resp = await fetch("/api/realtime/sdp-exchange/", {
      method:"POST",
      headers:{ Authorization:`Bearer ${EPHEMERAL_KEY}`, "Content-Type":"application/sdp" },
      body: offer.sdp
    });
    const answerSdp = await resp.text();
    await pc.setRemoteDescription({ type:"answer", sdp: answerSdp });

    // Client-side VAD for barge-in (optional but useful)
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const src = audioCtx.createMediaStreamSource(mic);
    analyser = audioCtx.createAnalyser(); analyser.fftSize = 2048; src.connect(analyser);

    const data = new Uint8Array(analyser.fftSize);
    const loop = () => {
      analyser.getByteTimeDomainData(data);
      let sum=0; for(let i=0;i<data.length;i++){ const v=(data[i]-128)/128; sum+=v*v; }
      const rms = Math.sqrt(sum/data.length);

      const speakingNow = rms > 0.12; // 환경에 맞게 조절
      if (speakingNow && !speaking) {
        if (!vadStart) vadStart = performance.now();
        if (performance.now() - vadStart > 500) {
          speaking = true;
          // 사용자 라인을 최소한 남겨 디버깅에 도움
          if (!userLine) userLine = appendLine("user:", "(speaking…)", "user");
          // 모델이 말하는 중이면 끊기
          const now = performance.now();
          if (!lastCancelAt || now - lastCancelAt > 1000) {
            try { dc?.send(JSON.stringify({ type:"response.cancel" })); } catch {}
            lastCancelAt = now;
            logSys("interrupt (barge-in)");
          }
        }
      } else if (!speakingNow) {
        vadStart = 0; speaking = false;
      }
      rafId = requestAnimationFrame(loop);
    };
    rafId = requestAnimationFrame(loop);

    ui("connected");
    logSys("Ready.");
  }

  function stopRtc(){
    if (rafId) cancelAnimationFrame(rafId); rafId = null;

    try { dc && dc.close && dc.close(); } catch {}
    dc = null;

    if (pc) {
      try { pc.getSenders().forEach(s => { try { s.track && s.track.stop(); } catch {} }); } catch {}
      try { pc.close(); } catch {}
    }
    pc = null;

    if (mic) { mic.getTracks().forEach(t => t.stop()); mic = null; }
    if (audioCtx) { try { audioCtx.close(); } catch {} audioCtx = null; }

    ui("stopped");
    logSys("Stopped.");
    // 진행 중 버퍼 초기화
    userLine = null; userBuf = "";
    botLine  = null; botBuf  = "";
  }

  // ===== DataChannel event parser =====
  function handleDCMessage(raw) {
    let msg; try { msg = JSON.parse(raw); } catch { return; }
    const t = String(msg.type || "");

    // -------- 사용자 전사(서버 발 이벤트) --------
    // input_audio_transcription.delta/completed 를 우선 처리
    if (t.startsWith("input_audio_transcription.")) {
      if (t.endsWith(".delta")) {
        const chunk = (msg.delta || msg.text || msg.transcript || "").toString();
        if (chunk) userDelta(chunk);
        // logEvt(t + " " + chunk); // 원하면 주석 해제
        return;
      }
      if (t.endsWith(".completed")) {
        const finalText = (msg.transcript || msg.text || "").toString();
        userFinal(finalText);
        // logEvt(t + " " + finalText);
        return;
      }
    }

    // -------- CarePill 텍스트(어시스턴트) --------
    if (t.startsWith("response.")) {
      if (t.includes(".delta") || t.includes(".output") || t.includes(".content")) {
        const chunk = (msg.delta || msg.output_text || msg.text || msg.content || msg.data || "").toString();
        if (chunk) botDelta(chunk);
        // logEvt(t + " " + chunk);
        return;
      }
      if (t.endsWith(".completed")) {
        const finalText = (msg.output_text || msg.text || msg.content || "").toString();
        botFinal(finalText);
        // logEvt(t + " " + finalText);
        return;
      }
    }

    // -------- 그 외 이벤트는 시스템 로그로 남김 --------
    logEvt(t);
  }

  function handleDCMessage(raw) {
  let msg; try { msg = JSON.parse(raw); } catch { return; }
  const t = String(msg.type || "");

  // 0) 유저 발화 시작/중지 신호에 맞춰 임시 줄 표시(디버깅용)
  if (t === "input_audio_buffer.speech_started") {
    if (!userLine) userLine = appendLine("user:", "(speaking…)", "user");
    return;
  }
  if (t === "input_audio_buffer.speech_stopped") {
    // 여기서는 확정하지 않음. completed에서 마무리
    return;
  }

  // 1) 사용자 전사: 대다수 모델이 'conversation.item.input_audio_transcription.*' 로 보냄
  //    (이전/다른 변형도 있으니 includes로 포괄 매칭)
  if (t.includes("input_audio_transcription.")) {
    // 델타/부분 전사
    if (t.endsWith(".delta")) {
      // 가능한 텍스트 후보를 광범위하게 수집
      const candidates = [
        msg.delta,
        msg.text,
        msg.transcript,
        msg.content,
        msg.data,
        // 중첩 경로들(모델/버전별 다름)
        msg?.item?.transcript,
        msg?.item?.text,
        msg?.item?.content,
        msg?.item?.data,
        // 배열 형태의 content에 transcript가 들어오는 경우
        Array.isArray(msg?.item?.content) ? msg.item.content.map(c => c?.text || c?.transcript).join(" ") : null
      ].filter(v => typeof v === "string" && v.trim().length);

      if (candidates.length) {
        userDelta(candidates[0]);
      } else {
        // 디버깅용으로 생긴 그대로 보고 싶으면 주석 해제
        // logEvt("no-user-delta-text " + JSON.stringify(msg));
      }
      return;
    }

    // 완료 전사
    if (t.endsWith(".completed")) {
      const candidates = [
        msg.transcript,
        msg.text,
        msg.content,
        msg.data,
        msg?.item?.transcript,
        msg?.item?.text,
        Array.isArray(msg?.item?.content) ? msg.item.content.map(c => c?.text || c?.transcript).join(" ") : null
      ].filter(v => typeof v === "string" && v.trim().length);

      if (candidates.length) {
        userFinal(candidates[0]);
      } else {
        // 전사 본문이 비어도 줄은 고정
        userFinal("");
        // logEvt("no-user-final-text " + JSON.stringify(msg));
      }
      return;
    }
  }

  // 2) CarePill 텍스트: response.*
  if (t.startsWith("response.")) {
    if (t.includes(".delta") || t.includes(".output") || t.includes(".content")) {
      const candidates = [
        msg.delta, msg.output_text, msg.text, msg.content, msg.data,
        msg?.item?.text, msg?.item?.content
      ].filter(v => typeof v === "string" && v.trim().length);
      if (candidates.length) botDelta(candidates[0]);
      return;
    }
    if (t.endsWith(".completed")) {
      const candidates = [
        msg.output_text, msg.text, msg.content,
        msg?.item?.text, msg?.item?.content
      ].filter(v => typeof v === "string" && v.trim().length);
      botFinal(candidates[0] || "");
      return;
    }
  }

  // 3) 나머지는 이벤트 라인으로 그대로 출력
  logEvt(t);
}





  // ===== Bind =====
  document.addEventListener("DOMContentLoaded", () => {
    ui("idle");
    elStart.addEventListener("click", () => {
      startRtc().catch(err => { logSys("start error: " + (err.message || err)); ui("stopped"); });
    });
    elStop.addEventListener("click",  stopRtc);
    window.addEventListener("beforeunload", stopRtc);
  });
})();
