// static/carepill/js/summary_overlay.js  (HARDENED + RETRY + DIAG + DOWNLOAD LINK)
(function () {
  // ===== util: banner/logger =====
  function banner(msg, color) {
    try {
      let b = document.getElementById("cp-summary-banner");
      if (!b) {
        b = document.createElement("div");
        b.id = "cp-summary-banner";
        b.style.cssText =
          "position:fixed;left:10px;bottom:10px;z-index:2147483647;padding:6px 10px;border-radius:6px;" +
          "color:#fff;background:" + (color||"#c00") + ";font:12px/1.3 system-ui, sans-serif;" +
          "box-shadow:0 2px 8px rgba(0,0,0,.2);";
        document.body.appendChild(b);
      }
      b.textContent = msg;
      b.style.background = color || "#c00";
      return b;
    } catch(e){ console.error("[cp-err] banner", e); }
  }
  const log = (...a)=>console.log("[cp]", ...a);
  const err = (...a)=>console.error("[cp-err]", ...a);

  // ===== state =====
  let overlay, panel, elSummary, elRaw, elStatus, elDebug, btnCopy;
  let summaryBtn, startBtn, stopBtn, chatLog;
  const transcript = [];

  // ===== robust: waitFor essentials =====
  function waitFor(fn, timeoutMs=10000, every=300){
    const t0 = Date.now();
    return new Promise((resolve, reject)=>{
      (function tick(){
        try{
          const ok = fn();
          if (ok) return resolve(ok);
        }catch(_){}
        if (Date.now()-t0>timeoutMs) return reject(new Error("wait timeout"));
        setTimeout(tick, every);
      })();
    });
  }

  // ===== role detection =====
  function roleFromNode(node) {
    const t = (node.textContent || "").trim();
    if (!t) return null;
    const L = t.toLowerCase();
    if (t.startsWith("사용자:") || L.startsWith("user:")) return "user";
    if (t.startsWith("케어필:") || L.startsWith("carepill:")) return "assistant";
    if (node.dataset && node.dataset.role) return node.dataset.role;
    if (node.classList && node.classList.contains("user")) return "user";
    if (node.classList && node.classList.contains("assistant")) return "assistant";
    return null;
  }

  function pushIfNew(node){
    const text = (node.textContent || "").trim();
    const role = roleFromNode(node);
    if (!text || !role) return;
    const last = transcript[transcript.length-1];
    if (last && last.text===text && last.role===role) return;
    transcript.push({role, text});
  }

  function toLines(){
    const out=[];
    for(const x of transcript){
      if (!x || typeof x.text !== "string") continue;
      if (x.role!=="user" && x.role!=="assistant") continue;
      let t = String(x.text || "");
      t = t.replace(/^\s*(user|사용자)\s*:\s*/i, "");
      t = t.replace(/^\s*(carepill|케어필)\s*:\s*/i, "");
      t = t.trim();
      if (!t) continue;
      out.push( (x.role==="user"?"User":"CarePill") + ": " + t );
    }
    return out;
  }

  // ===== overlay build =====
  function ensureOverlay(){
    if (overlay) return;
    overlay = document.createElement("div");
    overlay.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:2147483646;display:none;";
    panel = document.createElement("div");
    panel.style.cssText = "max-width:860px;margin:60px auto;background:#fff;border-radius:12px;padding:16px;" +
                          "box-shadow:0 10px 30px rgba(0,0,0,.25);font:14px/1.5 system-ui,sans-serif";
    panel.innerHTML = `
      <h2 style="margin:0 0 6px 0;">이번 대화 3줄 요약</h2>
      <p style="margin:0 0 10px 0;color:#555;">요약을 확인한 뒤 저장할 수 있습니다.</p>
      <pre id="cp-summary" style="white-space:pre-wrap;margin-bottom:8px;border:1px solid #eee;border-radius:8px;padding:8px;"></pre>
      <details open><summary>대화 원문 미리보기</summary><pre id="cp-raw" style="white-space:pre-wrap;border:1px solid #eee;border-radius:8px;padding:8px;"></pre></details>
      <div style="display:flex;gap:8px;margin-top:12px;">
        <button id="cp-yes" style="padding:8px 12px;border-radius:8px;border:1px solid #ddd;background:#0a0a0a;color:#fff">예, 저장</button>
        <button id="cp-no"  style="padding:8px 12px;border-radius:8px;border:1px solid #ddd;background:#888;color:#fff">아니오</button>
        <button id="cp-voice" style="padding:8px 12px;border-radius:8px;border:1px solid #ddd;background:#555;color:#fff">음성</button>
        <div id="cp-status" style="align-self:center;margin-left:8px;color:#666;"></div>
      </div>
      <details open style="margin-top:8px;"><summary>디버그 정보</summary>
        <pre id="cp-debug" style="white-space:pre-wrap;border:1px dashed #ccc;border-radius:8px;padding:8px;max-height:220px;overflow:auto;"></pre>
        <button id="cp-copy" style="margin-top:6px;padding:6px 10px;border:1px solid #ddd;border-radius:8px;background:#f5f5f5">진단 정보 복사</button>
      </details>
    `;
    overlay.appendChild(panel);
    document.body.appendChild(overlay);

    elSummary = panel.querySelector("#cp-summary");
    elRaw     = panel.querySelector("#cp-raw");
    elStatus  = panel.querySelector("#cp-status");
    elDebug   = panel.querySelector("#cp-debug");
    btnCopy   = panel.querySelector("#cp-copy");

    panel.querySelector("#cp-no").onclick = () => {
      elStatus.textContent = "저장을 취소했습니다.";
      setTimeout(()=> overlay.style.display="none", 300);
    };
    panel.querySelector("#cp-yes").onclick = () => saveNow();
    panel.querySelector("#cp-voice").onclick = () => {
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SR) { elStatus.textContent="이 브라우저는 음성 인식을 지원하지 않습니다."; return; }
      const rec = new SR(); rec.lang="ko-KR";
      rec.onresult = (e) => {
        const said = (e.results[0][0].transcript || "").trim();
        if (/^(예|네|응|맞|저장|yes|yep|ok|okay)\b/i.test(said)) panel.querySelector("#cp-yes").click();
        else if (/^(아니오|아니|노|취소|no|nope|cancel)\b/i.test(said)) panel.querySelector("#cp-no").click();
        else elStatus.textContent = `인식: "${said}" (예/아니오로 대답해 주세요)`;
      };
      rec.onerror = (e)=> elStatus.textContent="음성 인식 에러: "+(e.error||"");
      rec.start(); elStatus.textContent="음성 대기 중...";
    };
    if (btnCopy) btnCopy.onclick = async () => {
      try { await navigator.clipboard.writeText(elDebug ? elDebug.textContent : ""); elStatus.textContent="디버그 복사 완료."; }
      catch { elStatus.textContent="복사 실패. 콘솔 확인."; }
    };
  }

  function attachCollector(){
    Array.from(chatLog.children || []).forEach(pushIfNew);
    const mo = new MutationObserver((mutList) => {
      mutList.forEach(m => (m.addedNodes||[]).forEach(n=>{ if(n.nodeType===1) pushIfNew(n); }));
    });
    mo.observe(chatLog, { childList:true, subtree:false });
    log("collector attached; initial:", transcript.length);
  }

  async function summarizeNow(){
    try{
      ensureOverlay();
      elStatus.textContent = "요약 중...";
      const lines = toLines();
      elRaw.textContent = lines.join("\n");
      if (elDebug) elDebug.textContent = "request.lines_count=" + lines.length + "\n" + (lines.slice(-5).join("\n") || "(no lines)");
      console.time("[summary] fetch");
      const r = await fetch("/api/conversation/summarize_and_save/?debug=1",{
        method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({ lines, save:false, meta:{} })
      });
      const j = await r.json().catch(()=> ({}));
      console.timeEnd("[summary] fetch");
      if (!r.ok) {
        elSummary.textContent="";
        elStatus.textContent = "요약 실패: " + (j.detail || r.status);
        if (elDebug) elDebug.textContent += "\n\n" + JSON.stringify(j, null, 2);
        err("summary fail", j);
        return;
      }
      elSummary.textContent = (j.summary_text || "").trim() || "(요약이 비어 있습니다.)";
      elStatus.textContent = "요약 완료. 저장 여부를 선택하세요.";
      if (elDebug) elDebug.textContent += "\n\n" + JSON.stringify(j.debug || {}, null, 2);
      log("summary ok");
    } catch(e){
      console.timeEnd("[summary] fetch");
      ensureOverlay();
      elStatus.textContent = "요약 실패: " + (e.message||"");
      if (elDebug) elDebug.textContent += "\n\nEXC: " + (e.stack||String(e));
      err("summary exc", e);
    }
  }

  async function saveNow(){
    try{
      elStatus.textContent = "저장 중...";
      const lines = toLines();
      const meta = {
        title: (lines[0] ? lines[0].slice(0,20) : "carepill_session"),
        ended_at: new Date().toISOString().replace(/[-:]/g,"").slice(0,15)
      };
      if (elDebug) elDebug.textContent += "\n\nsave meta=" + JSON.stringify(meta);
      console.time("[save] fetch");
      const r = await fetch("/api/conversation/summarize_and_save/?debug=1",{
        method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({ lines, save:true, meta })
      });
      const j = await r.json().catch(()=> ({}));
      console.timeEnd("[save] fetch");
      if (!r.ok){
        elStatus.textContent = "저장 실패: " + (j.detail || r.status);
        if (elDebug) elDebug.textContent += "\n\n" + JSON.stringify(j, null, 2);
        err("save fail", j);
        return;
      }

      if (j.saved) {
        const linkA = j.download_url ? `<a href="${j.download_url}" target="_blank" rel="noopener">.txt 다운로드</a>` : "";
        const linkB = j.path ? ` / 보기: <a href="${j.path}" target="_blank" rel="noopener">${j.file_name || "열기"}</a>` : "";
        elStatus.innerHTML = `저장 완료 ✔ ${linkA}${linkB}`;
      } else {
        elStatus.textContent = "저장에 실패했습니다.";
      }

      if (elDebug) elDebug.textContent += "\n\n" + JSON.stringify(j.debug || {}, null, 2);
      log("save ok", j.path);
    } catch(e){
      console.timeEnd("[save] fetch");
      elStatus.textContent = "저장 실패: " + (e.message||"");
      if (elDebug) elDebug.textContent += "\n\nEXC: " + (e.stack||String(e));
      err("save exc", e);
    }
  }

  function ensureSummaryButton(){
    if (!summaryBtn) summaryBtn = document.getElementById("openSummary");
    if (!summaryBtn){
      summaryBtn = document.createElement("button");
      summaryBtn.id = "openSummary";
      summaryBtn.type = "button";
      summaryBtn.textContent = "대화 요약";
      summaryBtn.className = (startBtn && startBtn.className) ? startBtn.className : "primary-btn";
      if (startBtn && startBtn.parentNode) {
        startBtn.insertAdjacentText("afterend"," ");
        startBtn.insertAdjacentElement("afterend", summaryBtn);
      } else {
        banner("startRtc not found; button pinned to body", "#c2185b");
        document.body.appendChild(summaryBtn);
      }
    }
    summaryBtn.addEventListener("click", () => { ensureOverlay(); overlay.style.display="block"; summarizeNow(); }, {once:false});
  }

  function bootOnce(){
    chatLog = document.querySelector("#chatLog");
    startBtn = document.getElementById("startRtc");
    stopBtn  = document.getElementById("stopRtc");
    if (!chatLog) return false;
    attachCollector();
    ensureOverlay();
    ensureSummaryButton();
    if (stopBtn) stopBtn.addEventListener("click", ()=> setTimeout(()=>{ overlay.style.display="block"; summarizeNow(); }, 120));
    banner("Summary Ready ✓", "#2e7d32");
    setTimeout(()=>{ const b=document.getElementById("cp-summary-banner"); if(b&&b.parentNode) b.parentNode.removeChild(b); }, 3500);
    // dev diag
    window.cpSummary = { open: ()=>{ ensureOverlay(); overlay.style.display="block"; summarizeNow(); }, lines: ()=>toLines(), transcript };
    return true;
  }

  function startBoot(){
    if (bootOnce()) return;
    banner("Waiting DOM (#chatLog/#startRtc)…", "#d32f2f");
    waitFor(()=> {
      chatLog = document.querySelector("#chatLog");
      return !!chatLog;
    }, 15000, 250).then(()=>{
      bootOnce();
    }).catch(()=>{
      banner("FAIL: #chatLog not found. Fix selector.", "#c2185b");
      err("Cannot find #chatLog. Edit selector or run after template renders.");
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", startBoot);
  } else {
    startBoot();
  }
})();
