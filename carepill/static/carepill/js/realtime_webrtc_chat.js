// GPT Realtime (WebRTC) with LIVE chat rendering — CarePill FINAL
// - 에페메럴 키(client_secret.value 또는 value) 모두 지원
// - DataChannel 이벤트 파싱 및 채팅 스트리밍 렌더링
// - CSRF 토큰 지원
// - SDP 교환 안정화 및 상세 디버깅 로그 추가

(() => {
  const statusEl    = document.getElementById('rt-status');
  const startBtn    = document.getElementById('startRtc');
  const stopBtn     = document.getElementById('stopRtc');
  const remoteAudio = document.getElementById('remoteAudio');
  const chatLog     = document.getElementById('chatLog');

  let pc = null;
  let micStream = null;
  let dc = null;
  let currentAssistantEl = null;

  const setStatus = (m) => { statusEl.textContent = m; console.log('[RT]', m); };
  const scrollToBottom = () => { chatLog.scrollTop = chatLog.scrollHeight; };

  function bubble(role, text = '') {
    const wrap = document.createElement('div');
    wrap.className = `chat-bubble ${role === 'assistant' ? 'bot' : 'user'}`;
    wrap.style.margin = '10px 0';
    wrap.style.whiteSpace = 'pre-wrap';
    wrap.textContent = text;
    chatLog.appendChild(wrap);
    scrollToBottom();
    return wrap;
  }

  function addUserText(text) {
    bubble('user', text || '(음성 인식 중)');
  }

  function startAssistantStream() {
    currentAssistantEl = bubble('assistant', '');
  }

  function appendAssistantDelta(delta) {
    if (!currentAssistantEl) startAssistantStream();
    currentAssistantEl.textContent += delta;
    scrollToBottom();
  }

  function completeAssistantTurn() {
    currentAssistantEl = null;
  }

  // CSRF 토큰 유틸
  function getCookie(name) {
    const v = document.cookie.split(';').map(c => c.trim());
    for (const c of v) {
      if (c.startsWith(name + '=')) return decodeURIComponent(c.slice(name.length + 1));
    }
    return null;
  }

  // === 핵심: Realtime 시작 ===
  async function startRealtime() {
    try {
      setStatus('세션 토큰 요청 중…');

      // CSRF 헤더
      const csrftoken = getCookie('csrftoken');
      const sessResp = await fetch('/api/realtime/session/', {
        method: 'POST',
        headers: csrftoken ? { 'X-CSRFToken': csrftoken } : {},
        credentials: 'same-origin',
      });

      if (!sessResp.ok) {
        const errText = await sessResp.text().catch(() => '(no body)');
        console.error('[SESSION FAIL]', sessResp.status, errText);
        throw new Error('세션 발급 실패');
      }

      const raw = await sessResp.text();
      console.log('[SESSION RAW]', raw);

      let session;
      try {
        session = JSON.parse(raw);
      } catch (e) {
        console.error('[SESSION PARSE ERROR]', e);
        throw new Error('세션 응답 JSON 파싱 실패');
      }

      const EPHEMERAL_KEY = session?.client_secret?.value || session?.value;
      console.log('[EPHEMERAL_KEY]', EPHEMERAL_KEY);
      if (!EPHEMERAL_KEY || typeof EPHEMERAL_KEY !== 'string') {
        console.error('[SESSION OBJECT]', session);
        throw new Error('에페메럴 키 없음');
      }

      // 1) 마이크 권한
      setStatus('마이크 연결 중…');
      micStream = await navigator.mediaDevices.getUserMedia({ audio: true });

      // 2) 피어 생성
      pc = new RTCPeerConnection();

      // 3) 원격 오디오 (AI 음성)
      pc.ontrack = (event) => {
        const [stream] = event.streams;
        remoteAudio.srcObject = stream;
      };

      // 4) 로컬 마이크 전송
      micStream.getAudioTracks().forEach(t => pc.addTrack(t, micStream));

      pc.addTransceiver('audio', { direction: 'recvonly' });



      // 5) DataChannel (이벤트)
      dc = pc.createDataChannel('oai-events');
      dc.onopen = () => {
        console.log('[RT] DataChannel opened');
        bubble('assistant', '안녕하세요! 마이크에 대고 말씀해 보세요. (여기에 실시간으로 표시됩니다)');
      };
      dc.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data);
          handleRealtimeEvent(msg);
        } catch {
          console.log('[RT] non-JSON DataChannel message:', e.data);
        }
      };

      // 6) SDP 오퍼 생성

      const offer = await pc.createOffer({
        offerToReceiveAudio: true,
        offerToReceiveVideo: false,
        voiceActivityDetection: true
      });

      await pc.setLocalDescription(offer);
      console.log('[LOCAL SDP OFFER]', offer.sdp.substring(0, 200) + '...'); // 앞부분만 찍기

      setStatus('OpenAI에 SDP 전송 중…');

      // 7) SDP 교환 (WebRTC)
      const resp = await fetch(
        'https://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview',
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${EPHEMERAL_KEY}`,
            'Content-Type': 'application/sdp',
            'Accept': 'application/sdp',
            'OpenAI-Beta': 'realtime=v1',
          },
          body: offer.sdp,
        }
      );

      if (!resp.ok) {
        const errText = await resp.text().catch(() => '(no body)');
        console.error('[SDP POST FAIL]', resp.status, errText);
        bubble('assistant', `⚠️ OpenAI 응답 오류: ${resp.status}\n${errText}`);
        throw new Error(`SDP 교환 실패 (${resp.status})`);
      }

      const answerSDP = await resp.text();
      console.log('[ANSWER SDP]', answerSDP.substring(0, 120) + '...');
      await pc.setRemoteDescription({ type: 'answer', sdp: answerSDP });

      startBtn.style.display = 'none';
      stopBtn.style.display = 'inline-block';
      setStatus('연결 완료! 말하면 바로 텍스트/음성으로 응답합니다.');
    } catch (err) {
      console.error('[RT ERROR]', err);
      setStatus('오류: ' + err.message);
      bubble('assistant', '연결 오류가 발생했어요. 잠시 후 다시 시도해 주세요.');
    }
  }

  async function stopRealtime() {
    try {
      if (pc) {
        pc.getSenders().forEach(s => s.track && s.track.stop());
        pc.getReceivers().forEach(r => r.track && r.track.stop());
        pc.close();
      }
      if (micStream) micStream.getTracks().forEach(t => t.stop());
      if (dc && dc.readyState === 'open') dc.close();
    } catch (e) {
      console.warn('[STOP ERROR]', e);
    }
    pc = null; micStream = null; dc = null; currentAssistantEl = null;
    startBtn.style.display = 'inline-block';
    stopBtn.style.display = 'none';
    setStatus('대기 중');
  }

  // === Realtime 이벤트 파싱 → 채팅 렌더링 ===
  function handleRealtimeEvent(msg) {
    const t = msg.type;

    if (t === 'response.delta' && typeof msg.delta === 'string') {
      appendAssistantDelta(msg.delta);
      return;
    }

    if (t === 'response.completed') {
      completeAssistantTurn();
      return;
    }

    if (t === 'conversation.item.created') {
      const item = msg.item || {};
      const role = item.role;
      let text = '';

      if (item.formatted?.text) text = item.formatted.text;
      else if (item.formatted?.audio_transcript) text = item.formatted.audio_transcript;

      if (role === 'user') {
        if (text) addUserText(text);
      } else if (role === 'assistant') {
        if (text) {
          startAssistantStream();
          appendAssistantDelta(text);
          completeAssistantTurn();
        }
      }
      return;
    }

    // console.log('[RT EVT]', msg);
  }

  startBtn.addEventListener('click', startRealtime);
  stopBtn.addEventListener('click',  stopRealtime);
})();
