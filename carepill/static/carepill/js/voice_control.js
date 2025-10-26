// CarePill: Voice Navigation (Command-Only Mode, ko-KR)
// - 버튼을 누르면 즉시 "명령 대기" 상태로 전환(웨이크워드 없음)
// - 여러 번 말해도 계속 인식(continuous) + 화면 디버깅 콘솔 + 음성(TTS) 피드백
// - 매칭 규칙에 따라 페이지 이동

(function () {
  const DEBUG = true;                    // 콘솔 로그 켜기
  const USE_TTS = true;                  // 음성 피드백 사용
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const synth = window.speechSynthesis;

  if (!SpeechRecognition) {
    alert("이 브라우저는 Web Speech API를 지원하지 않습니다.");
    return;
  }

  // ========== UI: 글로벌 버튼 + 디버그 콘솔 ==========
  const btn = document.createElement('button');
  btn.id = 'globalMicBtn';
  btn.textContent = '🎤 음성 명령 켜기';
  Object.assign(btn.style, {
    position: 'fixed', right: '28px', bottom: '28px',
    background: 'linear-gradient(90deg, #7fb3ff, #2b7cff)', color: '#fff',
    border: 'none', padding: '12px 20px', borderRadius: '24px',
    cursor: 'pointer', fontSize: '1rem', boxShadow: '0 6px 14px rgba(43,124,255,0.3)',
    zIndex: 9999
  });
  document.body.appendChild(btn);

  const panel = document.createElement('div');
  panel.id = 'voiceDebugPanel';
  panel.innerHTML = `
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
      <strong>Voice Console</strong>
      <span id="vc-badge" style="
        display:inline-block;padding:2px 8px;border-radius:10px;
        background:#bbb;color:#fff;font-size:.85rem;">OFF</span>
    </div>
    <div id="vc-state" style="font-size:.95rem;color:#333;">상태: 대기</div>
    <div id="vc-interim" style="font-size:.95rem;color:#666;margin-top:6px;">(interim 없음)</div>
    <div id="vc-last" style="font-size:.95rem;color:#111;margin-top:6px;">마지막 결과: -</div>
    <div id="vc-match" style="font-size:.95rem;color:#2b7cff;margin-top:6px;">매칭: -</div>
    <div id="vc-log" style="
      margin-top:10px;height:130px;overflow:auto;background:#fff;
      border:1px solid #eee;border-radius:8px;padding:8px;font-size:.9rem;"></div>
  `;
  Object.assign(panel.style, {
    position: 'fixed', right: '28px', bottom: '84px',
    width: '320px', maxWidth: '95vw',
    background: 'rgba(255,255,255,0.98)', backdropFilter: 'blur(3px)',
    border: '1px solid #e6e9f3', borderRadius: '12px',
    boxShadow: '0 6px 18px rgba(0,0,0,0.08)', padding: '12px',
    zIndex: 9999
  });
  document.body.appendChild(panel);

  const elBadge  = panel.querySelector('#vc-badge');
  const elState  = panel.querySelector('#vc-state');
  const elInter  = panel.querySelector('#vc-interim');
  const elLast   = panel.querySelector('#vc-last');
  const elMatch  = panel.querySelector('#vc-match');
  const elLog    = panel.querySelector('#vc-log');

  const log = (msg) => {
    if (DEBUG) console.log('[VOICE]', msg);
    const div = document.createElement('div');
    const ts = new Date().toLocaleTimeString();
    div.textContent = `[${ts}] ${msg}`;
    elLog.appendChild(div);
    elLog.scrollTop = elLog.scrollHeight;
  };

  const setBadge = (on) => {
    elBadge.textContent = on ? 'ON' : 'OFF';
    elBadge.style.background = on ? '#2b7cff' : '#bbb';
  };

  // ========== 인식기 설정 ==========
  const rec = new SpeechRecognition();
  rec.lang = 'ko-KR';
  rec.interimResults = true;   // 중간결과 표시
  rec.continuous = true;       // 여러번 말해도 계속 듣기

  let listening = false;

  // 명령 라우팅 규칙 (synonyms 포함)
  function routeFor(raw) {
    const t = raw.replace(/\s+/g, '').toLowerCase();

    const rules = [
      { name: 'SCAN',   go: '/scan/',  tests: ['약투입','약투입창','약투입페이지','약투입해','스캔','업로드','약봉지','투입'] },
      { name: 'MEDS',   go: '/meds/',  tests: ['현재있는약','현재약','약목록','보관약','보관중인약','내약'] },
      { name: 'VOICE',  go: '/voice/', tests: ['케어필과대화','대화','채팅','챗봇','보이스'] },
      { name: 'HOME',   go: '/',       tests: ['홈','메인','메뉴','처음','메인으로'] },
    ];

    for (const r of rules) {
      if (r.tests.some(k => t.includes(k))) return r;
    }
    return null;
  }

  function speak(text) {
    if (!USE_TTS) return;
    // ElevenLabs TTS 사용 (브라우저 speechSynthesis 대신)
    if (window.CarePillTTS) {
      window.CarePillTTS.speak(text).catch(err => {
        console.error('TTS 재생 실패:', err);
      });
    }
  }

  // 이벤트
  rec.addEventListener('start', () => {
    listening = true;
    setBadge(true);
    elState.textContent = '상태: 듣는 중(명령 대기)';
    log('listening start');
    btn.textContent = '🛑 음성 명령 끄기';
    btn.style.opacity = '0.8';
  });

  rec.addEventListener('end', () => {
    listening = false;
    setBadge(false);
    elState.textContent = '상태: 종료됨(자동 재시작)';
    log('listening end → auto restart');
    // 일부 브라우저는 자동 재시작 필요
    if (btn.dataset.on === '1') {
      try { rec.start(); } catch (_) {}
    } else {
      btn.textContent = '🎤 음성 명령 켜기';
      btn.style.opacity = '1';
      elState.textContent = '상태: 대기';
    }
  });

  rec.addEventListener('error', (e) => {
    log('error: ' + e.error);
    elState.textContent = '에러: ' + e.error;
    setBadge(false);
  });

  rec.addEventListener('result', (evt) => {
    let interim = '';
    let final = '';

    for (let i = evt.resultIndex; i < evt.results.length; i++) {
      const r = evt.results[i];
      if (r.isFinal) {
        final = r[0].transcript.trim();
        const conf = (r[0].confidence * 100).toFixed(1);
        elLast.textContent  = `마지막 결과: "${final}" (conf ${conf}%)`;
        elInter.textContent = '(interim 없음)';
        log(`final: "${final}" (${conf}%)`);

        const match = routeFor(final);
        if (match) {
          elMatch.textContent = `매칭: ${match.name} → ${match.go}`;
          speak(`${match.name === 'HOME' ? '홈으로' :
                 match.name === 'SCAN' ? '약 투입 페이지로' :
                 match.name === 'MEDS' ? '현재 있는 약 페이지로' :
                 '대화 페이지로'} 이동합니다.`);
          log(`navigate → ${match.go}`);
          setTimeout(() => { window.location.href = match.go; }, 150);
        } else {
          elMatch.textContent = '매칭: (없음) 규칙 불일치';
          speak('명령을 이해하지 못했어요. 다시 말씀해 주세요.');
        }
      } else {
        interim += r[0].transcript;
      }
    }

    if (interim) {
      elInter.textContent = `interim: ${interim}`;
      log(`interim: ${interim}`);
    }
  });

  // 버튼 토글
  btn.addEventListener('click', () => {
    if (btn.dataset.on === '1') {
      btn.dataset.on = '0';
      try { rec.stop(); } catch (_) {}
      speak('음성 명령을 종료합니다.');
      setBadge(false);
      btn.textContent = '🎤 음성 명령 켜기';
      btn.style.opacity = '1';
      elState.textContent = '상태: 대기';
    } else {
      btn.dataset.on = '1';
      elState.textContent = '상태: 시작 시도(권한 필요)';
      speak('음성 명령을 시작합니다.');
      try { rec.start(); } catch (e) {
        elState.textContent = '상태: 시작 실패 — 다시 눌러주세요';
        log('start failed: ' + e.message);
      }
    }
  });
})();
