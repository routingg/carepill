// --- CarePill: Wake-word Navigation (ko-KR) ---
// 모드 설명:
// - passive(대기): "케어필", "케어필아", "야 케어필" 중 하나를 인식하면 command 모드로 전환
// - command(명령): 이어지는 한 문장을 명령으로 해석하여 페이지 이동 후 다시 passive 복귀

(function () {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const synth = window.speechSynthesis;

  if (!SpeechRecognition) {
    console.warn("Web Speech API 미지원 브라우저입니다.");
    return;
  }

  // --------- UI ----------
  const micBtn = document.createElement('button');
  micBtn.id = 'globalMicBtn';
  micBtn.textContent = '🎤 음성 켜기';
  Object.assign(micBtn.style, {
    position: 'fixed', right: '30px', bottom: '30px',
    background: 'linear-gradient(90deg, #7fb3ff, #2b7cff)',
    color: '#fff', border: 'none', padding: '12px 22px',
    borderRadius: '24px', cursor: 'pointer', fontSize: '1rem',
    boxShadow: '0 6px 14px rgba(43,124,255,0.3)', zIndex: 9999
  });
  document.body.appendChild(micBtn);

  const statusBox = document.createElement('div');
  statusBox.id = 'voiceStatus';
  Object.assign(statusBox.style, {
    position: 'fixed', right: '36px', bottom: '74px',
    background: 'rgba(255,255,255,0.95)', color: '#333',
    borderRadius: '10px', padding: '6px 12px',
    boxShadow: '0 2px 6px rgba(0,0,0,0.1)', fontSize: '0.95rem',
    zIndex: 9999
  });
  statusBox.textContent = '대기 꺼짐';
  document.body.appendChild(statusBox);

  // --------- 상태 ----------
  let mode = 'idle';          // 'idle' | 'passive' | 'command'
  let listening = false;
  let commandTimeoutId = null;

  // 웨이크 워드 사전
  const wakeWords = ['케어필', '케어필아', '안녕', '안녕하세요', '야 케어필'];

  // 페이지 명령 매핑
  const commands = [
    { test: s => s.includes('약투입') || s.includes('약 투입'), go: '/scan/' },
    { test: s => s.includes('현재있는약') || s.includes('현재 있는 약'), go: '/meds/' },
    { test: s => s.includes('케어필과대화') || s.includes('대화'), go: '/voice/' },
    { test: s => s.includes('홈') || s.includes('메인'), go: '/' },
  ];

  // 전처리(공백 제거/소문자화)
  const norm = (t) => t.replace(/\s+/g, '').toLowerCase();

  // --------- 음성합성(선택) ----------
  function speak(text) {
    try {
      if (!synth) return;
      const u = new SpeechSynthesisUtterance(text);
      u.lang = 'ko-KR';
      u.rate = 1.0;
      synth.cancel();
      synth.speak(u);
    } catch (_) {}
  }

  // --------- 인식기 ----------
  const rec = new SpeechRecognition();
  rec.lang = 'ko-KR';
  rec.interimResults = false;
  rec.continuous = false; // 브라우저 특성상 end에서 재시작 루프

  rec.addEventListener('result', (evt) => {
    const text = evt.results[0][0].transcript.trim();
    const n = norm(text);
    // console.log('[ASR]', text);

    if (mode === 'passive') {
      // 웨이크워드 감지
      if (wakeWords.some(w => n.includes(norm(w)))) {
        statusBox.textContent = '웨이크워드 감지 → 명령 대기';
        speak('네, 말씀하세요.');
        switchToCommandMode();
      } else {
        statusBox.textContent = '대기 중(웨이크워드 인식 실패)';
      }
    } else if (mode === 'command') {
      // 명령 해석
      const hit = commands.find(c => c.test(n));
      if (hit) {
        statusBox.textContent = '이동: ' + hit.go;
        speak('이동합니다.');
        // 약간의 지연 후 이동(합성 겹침 방지)
        setTimeout(() => { window.location.href = hit.go; }, 200);
      } else {
        statusBox.textContent = `명령 인식 못함: ${text}`;
        speak('다시 말씀해 주세요.');
        // 명령 모드 유지(타임아웃 동안)
        restart();
      }
    }
  });

  rec.addEventListener('end', () => {
    listening = false;
    // mode에 따라 자동 재시작
    if (mode === 'passive' || mode === 'command') {
      restart();
    } else {
      statusBox.textContent = '대기 꺼짐';
      micBtn.textContent = '🎤 음성 켜기';
      micBtn.style.opacity = '1';
    }
  });

  rec.addEventListener('error', (e) => {
    statusBox.textContent = '에러: ' + e.error;
    // 네트워크/권한 이슈 등은 사용자가 다시 버튼으로 재시작
    listening = false;
  });

  // --------- 모드 전환 & 재시작 ----------
  function restart() {
    if (listening) return;
    try {
      rec.start();
      listening = true;
      micBtn.style.opacity = '0.7';
      if (mode === 'passive') statusBox.textContent = '🎙️ 웨이크워드 대기 중…';
      if (mode === 'command') statusBox.textContent = '🎙️ 명령 대기 중…';
    } catch (_) {
      // start() 중복 호출 등 에러시 무시
    }
  }

  function switchToPassiveMode() {
    mode = 'passive';
    clearTimeout(commandTimeoutId);
    commandTimeoutId = null;
    restart();
  }

  function switchToCommandMode() {
    mode = 'command';
    clearTimeout(commandTimeoutId);
    // 8초 동안 명령을 기다렸다가 자동 복귀
    commandTimeoutId = setTimeout(() => {
      speak('대기 모드로 돌아갑니다.');
      switchToPassiveMode();
    }, 8000);
    restart();
  }

  function startAll() {
    // 최초 1회: 사용자 제스처로 권한 취득 필요
    mode = 'passive';
    statusBox.textContent = '권한 요청 중…';
    try {
      rec.start();
      listening = true;
      micBtn.textContent = '🎤 대기 중(끄려면 클릭)';
      micBtn.style.opacity = '0.7';
      statusBox.textContent = '🎙️ 웨이크워드 대기 중…';
    } catch (e) {
      statusBox.textContent = '마이크 시작 실패. 다시 눌러주세요.';
    }
  }

  function stopAll() {
    mode = 'idle';
    clearTimeout(commandTimeoutId);
    commandTimeoutId = null;
    try { rec.stop(); } catch (_) {}
    listening = false;
    micBtn.textContent = '🎤 음성 켜기';
    micBtn.style.opacity = '1';
    statusBox.textContent = '대기 꺼짐';
  }

  // 버튼 토글
  micBtn.addEventListener('click', () => {
    if (mode === 'idle') startAll();
    else stopAll();
  });

  // (선택) 페이지 진입 시 안내 토스트
  setTimeout(() => {
    if (mode === 'idle') {
      statusBox.textContent = '버튼을 눌러 음성 대기를 켜세요';
    }
  }, 1200);
})();
