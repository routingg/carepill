(function () {
  // ===== DOM =====
  const $ = (id) => document.getElementById(id);
  const elStart = $("startRtc");
  const elStop = $("stopRtc");
  const elStatus = $("rt-status");
  const elAudio = $("remoteAudio");
  const elLog = $("chatLog");

  // ===== 옵션 (심플) =====
  const BARGE_IN = false;     // 말 끊기(바지-인) 끄기: false (원하면 true)
  const VAD_RMS = 0.13;       // 켤 경우 임계값
  const VAD_HOLD_MS = 500;    // 켤 경우 최소 지속 시간

  // ===== State =====
  let pc = null, dc = null, mic = null;
  let audioCtx = null, analyser = null, rafId = null;
  let speaking = false, vadStart = 0, lastCancelAt = 0;

  // 응답 중복 방지용
  const printedResponseIds = new Set();

  // ===== Log helpers =====
  function appendLine(prefix, text, role) {
    const div = document.createElement("div");
    if (role) div.dataset.role = role;
    div.textContent = (prefix ? prefix + " " : "") + (text ?? "");
    elLog.appendChild(div);
    elLog.scrollTop = elLog.scrollHeight;
    return div;
  }
  const logSys = (msg) => appendLine("SYS:", msg, "sys");
  const logEvt = (msg) => appendLine("EVT:", msg, "evt");

  // ===== UI =====
  function ui(state){
    const map = { idle:"대기 중", connecting:"연결 중…", connected:"연결됨", stopped:"종료됨" };
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

  // ===== WebRTC start =====
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

    // (선택) 바지-인: 심플모드에서는 기본 끔
    if (BARGE_IN) {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const src = audioCtx.createMediaStreamSource(mic);
      analyser = audioCtx.createAnalyser(); analyser.fftSize = 2048; src.connect(analyser);
      const data = new Uint8Array(analyser.fftSize);

      const loop = () => {
        analyser.getByteTimeDomainData(data);
        let sum=0; for(let i=0;i<data.length;i++){ const v=(data[i]-128)/128; sum+=v*v; }
        const rms = Math.sqrt(sum/data.length);
        const speakingNow = rms > VAD_RMS;
        if (speakingNow && !speaking) {
          if (!vadStart) vadStart = performance.now();
          if (performance.now() - vadStart > VAD_HOLD_MS) {
            speaking = true;
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
    }

    ui("connected");
    logSys("Ready.");
  }

  // ===== stop =====
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
    printedResponseIds.clear();
  }

  // ===== DC message (심플: 완료 이벤트만 텍스트로 찍기) =====
  function handleDCMessage(raw) {
    let msg; try { msg = JSON.parse(raw); } catch { return; }
    const t = String(msg.type || "");

    // 이벤트 그대로 보고 싶으면 주석 해제
    // logEvt(t);

    // 사용자 발화 표시 (완료만)
    if (t.includes("input_audio_transcription.") && t.endsWith(".completed")) {
      const text = msg.transcript || msg.text || msg?.item?.text || msg?.item?.transcript || "";
      if (text) appendLine("user:", text.trim(), "user");
      return;
    }
    // 전사 이벤트가 안 오는 경우 최소한의 표시
    if (t === "input_audio_buffer.speech_started") { logEvt("input_audio_buffer.speech_started"); return; }
    if (t === "input_audio_buffer.speech_stopped") { logEvt("input_audio_buffer.speech_stopped"); return; }

    // CarePill 응답: 한 응답당 1번만 출력(완료 기준)
    if (t.startsWith("response.")) {
      const id = (msg.response && msg.response.id) || null;

      // 오디오 자막이 있으면 그걸 우선 사용 (보통 가장 자연스러운 문장)
      if (t === "response.audio_transcript.done") {
        if (id && printedResponseIds.has(id)) return;
        const text = msg.transcript || msg.text || msg.output_text || "";
        if (text) {
          appendLine("carepill:", text.trim(), "assistant");
          if (id) printedResponseIds.add(id);
        }
        return;
      }

      // 일반 완료
      if (t === "response.done" || t.endsWith(".completed") || t.endsWith(".done")) {
        if (id && printedResponseIds.has(id)) return;
        const text = msg.output_text || msg.text || msg.content || "";
        if (text) {
          appendLine("carepill:", String(text).trim(), "assistant");
          if (id) printedResponseIds.add(id);
        }
        return;
      }

      // 그 외 상태 이벤트는 이벤트 로그로
      logEvt(t);
      return;
    }

    // 나머지
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
