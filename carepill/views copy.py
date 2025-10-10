import os, requests
from django.http import JsonResponse
from django.shortcuts import render

def home(request):  return render(request, "carepill/home.html")
def scan(request):  return render(request, "carepill/scan.html")
def meds(request):  return render(request, "carepill/meds.html")
def voice(request): return render(request, "carepill/voice.html")

def issue_ephemeral(request):
    r = requests.post(
        "https://api.openai.com/v1/realtime/sessions",
        headers={
            "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
            "Content-Type": "application/json",
            "OpenAI-Beta": "realtime=v1",
        },
        json={
            "model": "gpt-4o-mini-realtime-preview-2024-12-17",
            "voice": "verse",
            "modalities": ["audio", "text"],
            "turn_detection": {
                "type": "server_vad", 
                "create_response": True, 
                "silence_duration_ms": 500
            },
            "input_audio_transcription": {"model": "gpt-4o-mini-transcribe"},
            "instructions": (
                "You are 'CarePill', a voice-based medication assistant designed to help visually impaired users. "
                "Speak Korean with clear, precise pronunciation, like a professional news announcer. "
                "Provide guidance about medication usage, dosage, timing, and potential drug interactions. "
                "Offer emotional support and speak warmly, as if you are a trusted friend who cares about the user’s well-being. "
                "Keep your responses short, calm, and friendly, delivering them with confidence and kindness."
            ),
        },
        timeout=20,
    )

    try:
        data = r.json()
    except Exception:
        # OpenAI에서 예외적으로 비JSON이 오면 원문 전달
        return JsonResponse({"error": "upstream_non_json", "text": r.text}, status=r.status_code)

    if r.status_code != 200:
        # 에러 원문 그대로 반환
        return JsonResponse(data, status=r.status_code)

    # ✅ 스키마 정규화: 항상 {value, expires_at, session} 형태로 반환
    value = data.get("value") or (data.get("client_secret") or {}).get("value")
    expires_at = data.get("expires_at") or (data.get("client_secret") or {}).get("expires_at")
    session = data.get("session") or {"id": data.get("id"), "type": "realtime", "object": "realtime.session"}

    if not value:
        return JsonResponse({"error": "no_ephemeral_value", "upstream": data}, status=502)

    return JsonResponse({"value": value, "expires_at": expires_at, "session": session}, status=200)


import os, requests
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def realtime_sdp_exchange(request):
    """
    브라우저가 직접 OpenAI에 POST하지 않고, 서버가 대신 SDP를 교환해준다.
    - 요청 헤더 Authorization: Bearer <ephemeral_key> (클라가 전달)
    - 요청 body: offer SDP (text)
    - 응답 body: answer SDP (text)
    """
    if request.method != "POST":
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    # 브라우저가 준 에페메럴 키를 그대로 사용 (주의: 정식 OPENAI_API_KEY 아님)
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ek_"):  # 간단 검증
        return JsonResponse({"error": "missing_or_invalid_ephemeral"}, status=400)

    offer_sdp = request.body or b""
    if not offer_sdp:
        return JsonResponse({"error": "empty_offer_sdp"}, status=400)

    try:
        upstream = requests.post(
            "https://api.openai.com/v1/realtime?model=gpt-4o-mini-realtime-preview-2024-12-17",
            headers={
                "Authorization": auth,                   # Bearer ek_... (ephemeral)
                "Content-Type": "application/sdp",
                "OpenAI-Beta": "realtime=v1",
            },
            data=offer_sdp,
            timeout=20,
        )
    except requests.RequestException as e:
        return JsonResponse({"error": "upstream_network_error", "detail": str(e)}, status=502)

    # OpenAI는 answer SDP를 text로 반환
    return HttpResponse(upstream.text, status=upstream.status_code, content_type="application/sdp")






















# views.py
import os
import re
import json
import time
import uuid
import traceback
import datetime
import logging
import requests

from django.conf import settings
from django.http import JsonResponse, HttpResponse, Http404
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)

# ===== OpenAI 설정 =====
SUMMARIZER_MODEL = os.getenv("SUMMARIZER_MODEL", "gpt-4o-mini")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"


# ===== 파일명/저장 유틸 =====
def _sanitize_filename(name: str) -> str:
    if not isinstance(name, str):
        name = str(name or "session")
    name = name.strip()
    # 한글/영문/숫자/공백/일부 특수문자만 허용
    name = re.sub(r'[^0-9A-Za-z\u3131-\u318E\uAC00-\uD7A3 _\-.]', '_', name)
    name = name.replace(" ", "_")
    name = name[:80] or "session"
    # 확장자 보장
    if not name.lower().endswith(".txt"):
        name += ".txt"
    return name


def _save_txt(meta, summary_text, transcript_lines):
    """ media/conversations/에 .txt 저장하고 파일경로/URL/다운로드URL 반환 """
    media_root = getattr(settings, "MEDIA_ROOT", os.path.join(os.getcwd(), "media"))
    media_url  = getattr(settings, "MEDIA_URL", "/media/")
    base_dir   = os.path.join(media_root, "conversations")
    os.makedirs(base_dir, exist_ok=True)

    ts    = meta.get("ended_at") or datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    title = _sanitize_filename(meta.get("title") or "carepill_session")
    # 이미 title에 .txt가 들어가 있으므로 ts_ 접두사만
    fname = f"{ts}_{title}" if not title.startswith(ts + "_") else title

    fpath = os.path.join(base_dir, fname)                      # 실제 파일 경로
    furl  = media_url.rstrip("/") + "/conversations/" + fname  # /media/... 열람 URL
    download_url = "/api/conversation/download/?name=" + fname # 다운로드 URL

    content = []
    content.append("[3-line Summary]")
    content.append((summary_text or "").strip())
    content.append("")
    content.append("[Conversation]")
    content.extend(transcript_lines or [])
    with open(fpath, "w", encoding="utf-8") as f:
        f.write("\n".join(content))

    return {"file_name": fname, "path_fs": fpath, "path_url": furl, "download_url": download_url}


def _save_debug(rid, debug_obj):
    try:
        media_root = getattr(settings, "MEDIA_ROOT", os.path.join(os.getcwd(), "media"))
        base_dir   = os.path.join(media_root, "conversations")
        os.makedirs(base_dir, exist_ok=True)
        fname = f"_debug_{rid}.json"
        fpath = os.path.join(base_dir, fname)
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(debug_obj, f, ensure_ascii=False, indent=2)
        media_url  = getattr(settings, "MEDIA_URL", "/media/")
        furl  = media_url.rstrip("/") + "/conversations/" + fname
        return furl
    except Exception:
        return None


# ===== 다운로드 엔드포인트 (Content-Disposition) =====
@csrf_exempt
def api_conversation_download(request):
    """
    GET /api/conversation/download/?name=<파일명.txt>
    conversations 폴더 아래의 .txt만 다운로드로 제공
    """
    name = request.GET.get("name", "")
    if not name or "/" in name or "\\" in name or name.startswith("."):
        return JsonResponse({"error": "bad_name"}, status=400)
    if not name.lower().endswith(".txt"):
        return JsonResponse({"error": "bad_ext"}, status=400)

    base_dir = os.path.join(getattr(settings, "MEDIA_ROOT", os.path.join(os.getcwd(),"media")), "conversations")
    fpath = os.path.join(base_dir, name)
    if not os.path.exists(fpath):
        raise Http404("file not found")

    with open(fpath, "rb") as fp:
        resp = HttpResponse(fp.read(), content_type="text/plain; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{name}"'
    return resp


# ===== 3줄 요약 + 저장 (TXT 전용, 디버그 포함) =====
@csrf_exempt
def api_conversation_summarize_and_save(request):
    """
    payload:
      - transcript: [{role:"user|assistant|...","text":"..."}...]  (선택)
      - 또는 lines: ["User: ...","CarePill: ...", ...]             (권장)
      - save: true|false
      - meta: { title?: str, ended_at?: "YYYYMMDDTHHMMSS" }
      - debug: true|false   # 응답에 debug 포함

    response:
      - { "summary_text": str,
          "saved": bool,
          "path": str|null,          # /media/... 열람용 URL
          "download_url": str|null,  # 다운로드 URL (Content-Disposition)
          "file_name": str|null,
          "debug": {...}? }
    """
    rid = str(uuid.uuid4())[:8]
    t0 = time.time()

    if request.method != "POST":
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception as e:
        return JsonResponse({"error": "invalid_json", "detail": str(e)}, status=400)

    do_save    = bool(payload.get("save", False))
    meta       = payload.get("meta", {}) or {}
    debug_mode = bool(payload.get("debug") or request.GET.get("debug") == "1" or os.getenv("SUMMARY_DEBUG") == "1")

    # 입력 표준화: lines 우선, 없으면 transcript → lines로 변환
    lines = payload.get("lines")
    transcript = payload.get("transcript")
    if not lines:
        if not transcript or not isinstance(transcript, list):
            return JsonResponse({"error": "no_transcript_or_lines"}, status=400)
        lines = []
        for x in transcript:
            role = x.get("role")
            text = (x.get("text") or "").strip()
            if not text or role not in ("user", "assistant"):
                continue
            t = text
            # 앞단 접두사 제거
            t = re.sub(r'^\s*(user|사용자)\s*:\s*', '', t, flags=re.I)
            t = re.sub(r'^\s*(carepill|케어필)\s*:\s*', '', t, flags=re.I)
            prefix = "User" if role == "user" else "CarePill"
            lines.append(f"{prefix}: {t}")

    SAFE_MAX = 120
    lines = lines[-SAFE_MAX:]

    debug = {
        "request_id": rid,
        "lines_count": len(lines),
        "lines_first3": lines[:3],
        "lines_last3": lines[-3:],
        "model": SUMMARIZER_MODEL,
        "openai_status": None,
        "openai_elapsed_ms": None,
        "openai_preview": None,
        "saved_path": None,
        "server_elapsed_ms": None,
        "exception": None,
    }

    # 빈 대화 처리
    if not lines:
        summary_text = "대화 요약: (비어 있음)"
        saved_info = None
        if do_save:
            saved_info = _save_txt(meta, summary_text, [])
            debug["saved_path"] = saved_info["path_url"]
        debug["server_elapsed_ms"] = int((time.time() - t0) * 1000)
        resp = {
            "summary_text": summary_text,
            "saved": bool(saved_info),
            "path": (saved_info or {}).get("path_url") if saved_info else None,
            "download_url": (saved_info or {}).get("download_url") if saved_info else None,
            "file_name": (saved_info or {}).get("file_name") if saved_info else None,
        }
        if debug_mode: resp["debug"] = debug
        return JsonResponse(resp, status=200)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return JsonResponse({"error": "missing_api_key"}, status=500)

    # OpenAI 호출
    prompt = (
        "아래는 사용자(User)와 케어필(CarePill)의 대화 로그입니다.\n"
        "핵심만 한국어로 '3줄 요약'을 작성하세요. 각 줄은 1문장으로 간결하게.\n"
        "가능하면 주제/요청/응답 또는 감정/행동계획이 드러나게 정리하세요.\n\n"
        "대화:\n" + "\n".join(lines)
    )

    t1 = time.time()
    try:
        resp = requests.post(
            OPENAI_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": SUMMARIZER_MODEL,
                "messages": [
                    {"role": "system", "content": "너는 한국어 대화 요약 도우미다. 결과는 텍스트(3줄)로만 답한다."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
            },
            timeout=60,
        )
        debug["openai_status"] = resp.status_code
        debug["openai_elapsed_ms"] = int((time.time() - t1) * 1000)

        if resp.status_code != 200:
            debug["openai_preview"] = resp.text[:800]
            debug["server_elapsed_ms"] = int((time.time() - t0) * 1000)
            if debug_mode: _save_debug(rid, debug)
            out = {"error": "summarize_failed", "detail": f"upstream {resp.status_code}", "upstream": resp.text}
            if debug_mode: out["debug"] = debug
            return JsonResponse(out, status=502)

        data = resp.json()
        # 응답 일부 프리뷰 보존
        try:
            debug["openai_preview"] = json.dumps(data, ensure_ascii=False)[:800]
        except Exception:
            debug["openai_preview"] = str(data)[:800]

        summary_text = (data["choices"][0]["message"]["content"] or "").strip()
        if not summary_text:
            summary_text = "대화 요약: (생성 실패)"
    except Exception as e:
        debug["exception"] = (traceback.format_exc() or str(e))[-1000:]
        debug["server_elapsed_ms"] = int((time.time() - t0) * 1000)
        if debug_mode: _save_debug(rid, debug)
        out = {"error": "summarize_failed", "detail": str(e)}
        if debug_mode: out["debug"] = debug
        return JsonResponse(out, status=502)

    # 저장(옵션)
    saved_info = None
    if do_save:
        saved_info = _save_txt(meta, summary_text, lines)
        debug["saved_path"] = saved_info["path_url"]

    debug["server_elapsed_ms"] = int((time.time() - t0) * 1000)
    if debug_mode: _save_debug(rid, debug)

    resp_out = {
        "summary_text": summary_text,
        "saved": bool(saved_info),
        "path": (saved_info or {}).get("path_url") if saved_info else None,
        "download_url": (saved_info or {}).get("download_url") if saved_info else None,
        "file_name": (saved_info or {}).get("file_name") if saved_info else None,
    }
    if debug_mode: resp_out["debug"] = debug
    return JsonResponse(resp_out, status=200)












import os, re, json, time, uuid, traceback, datetime, logging, requests
from django.conf import settings
from django.http import JsonResponse, HttpResponse, Http404
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)

# -----------------------------
# 기본 페이지
# -----------------------------
def home(request):  return render(request, "carepill/home.html")

def scan(request):  return render(request, "carepill/scan.html")

def meds(request):  return render(request, "carepill/meds.html")

def voice(request): return render(request, "carepill/voice.html")

# -----------------------------
# Realtime Ephemeral & SDP Relay (기존 유지)
# -----------------------------
def issue_ephemeral(request):
    r = requests.post(
        "https://api.openai.com/v1/realtime/sessions",
        headers={
            "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
            "Content-Type": "application/json",
            "OpenAI-Beta": "realtime=v1",
        },
        json={
            "model": "gpt-4o-mini-realtime-preview-2024-12-17",
            "voice": "verse",
            "modalities": ["audio", "text"],
            "turn_detection": {"type": "server_vad", "create_response": True, "silence_duration_ms": 500},
            "input_audio_transcription": {"model": "gpt-4o-mini-transcribe"},
            "instructions": (
                "You are 'CarePill', a voice-based medication assistant designed to help visually impaired users. "
                "Speak Korean with clear, precise pronunciation, like a professional news announcer. "
                "Provide guidance about medication usage, dosage, timing, and potential drug interactions. "
                "Offer emotional support and speak warmly, as if you are a trusted friend who cares about the user’s well-being. "
                "Keep your responses short, calm, and friendly, delivering them with confidence and kindness."
            ),
        }, timeout=20,
    )
    try:
        data = r.json()
    except Exception:
        return JsonResponse({"error": "upstream_non_json", "text": r.text}, status=r.status_code)
    if r.status_code != 200:
        return JsonResponse(data, status=r.status_code)

    value = data.get("value") or (data.get("client_secret") or {}).get("value")
    expires_at = data.get("expires_at") or (data.get("client_secret") or {}).get("expires_at")
    session = data.get("session") or {"id": data.get("id"), "type": "realtime", "object": "realtime.session"}
    if not value:
        return JsonResponse({"error": "no_ephemeral_value", "upstream": data}, status=502)
    return JsonResponse({"value": value, "expires_at": expires_at, "session": session}, status=200)

@csrf_exempt
def realtime_sdp_exchange(request):
    if request.method != "POST":
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ek_"):
        return JsonResponse({"error": "missing_or_invalid_ephemeral"}, status=400)
    offer_sdp = request.body or b""
    if not offer_sdp:
        return JsonResponse({"error": "empty_offer_sdp"}, status=400)
    try:
        upstream = requests.post(
            "https://api.openai.com/v1/realtime?model=gpt-4o-mini-realtime-preview-2024-12-17",
            headers={"Authorization": auth, "Content-Type": "application/sdp", "OpenAI-Beta": "realtime=v1"},
            data=offer_sdp, timeout=20,
        )
    except requests.RequestException as e:
        return JsonResponse({"error": "upstream_network_error", "detail": str(e)}, status=502)
    return HttpResponse(upstream.text, status=upstream.status_code, content_type="application/sdp")

# -----------------------------
# 대화 3줄 요약 + TXT 저장(기존 유지)
# -----------------------------
SUMMARIZER_MODEL = os.getenv("SUMMARIZER_MODEL", "gpt-4o-mini")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

def _sanitize_filename(name: str) -> str:
    if not isinstance(name, str): name = str(name or "session")
    name = name.strip()
    name = re.sub(r'[^0-9A-Za-z\u3131-\u318E\uAC00-\uD7A3 _\-.]', '_', name).replace(" ", "_")
    name = name[:80] or "session"
    if not name.lower().endswith(".txt"): name += ".txt"
    return name

def _save_txt(meta, summary_text, transcript_lines):
    media_root = getattr(settings, "MEDIA_ROOT", os.path.join(os.getcwd(), "media"))
    media_url  = getattr(settings, "MEDIA_URL", "/media/")
    base_dir   = os.path.join(media_root, "conversations")
    os.makedirs(base_dir, exist_ok=True)
    ts    = meta.get("ended_at") or datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    title = _sanitize_filename(meta.get("title") or "carepill_session")
    fname = f"{ts}_{title}" if not title.startswith(ts + "_") else title
    fpath = os.path.join(base_dir, fname)
    furl  = media_url.rstrip("/") + "/conversations/" + fname
    download_url = "/api/conversation/download/?name=" + fname
    content = ["[3-line Summary]", (summary_text or "").strip(), "", "[Conversation]"] + (transcript_lines or [])
    with open(fpath, "w", encoding="utf-8") as f: f.write("\n".join(content))
    return {"file_name": fname, "path_fs": fpath, "path_url": furl, "download_url": download_url}

def _save_debug(rid, debug_obj):
    try:
        media_root = getattr(settings, "MEDIA_ROOT", os.path.join(os.getcwd(), "media"))
        base_dir   = os.path.join(media_root, "conversations")
        os.makedirs(base_dir, exist_ok=True)
        fname = f"_debug_{rid}.json"
        fpath = os.path.join(base_dir, fname)
        with open(fpath, "w", encoding="utf-8") as f: json.dump(debug_obj, f, ensure_ascii=False, indent=2)
        media_url  = getattr(settings, "MEDIA_URL", "/media/")
        furl  = media_url.rstrip("/") + "/conversations/" + fname
        return furl
    except Exception:
        return None

@csrf_exempt
def api_conversation_download(request):
    name = request.GET.get("name", "")
    if not name or "/" in name or "\\" in name or name.startswith("."):
        return JsonResponse({"error": "bad_name"}, status=400)
    if not name.lower().endswith(".txt"):
        return JsonResponse({"error": "bad_ext"}, status=400)
    base_dir = os.path.join(getattr(settings, "MEDIA_ROOT", os.path.join(os.getcwd(),"media")), "conversations")
    fpath = os.path.join(base_dir, name)
    if not os.path.exists(fpath): raise Http404("file not found")
    with open(fpath, "rb") as fp:
        resp = HttpResponse(fp.read(), content_type="text/plain; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{name}"'
    return resp

@csrf_exempt
def api_conversation_summarize_and_save(request):
    rid = str(uuid.uuid4())[:8]
    t0 = time.time()
    if request.method != "POST":
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception as e:
        return JsonResponse({"error": "invalid_json", "detail": str(e)}, status=400)

    do_save    = bool(payload.get("save", False))
    meta       = payload.get("meta", {}) or {}
    debug_mode = bool(payload.get("debug") or request.GET.get("debug") == "1" or os.getenv("SUMMARY_DEBUG") == "1")

    lines = payload.get("lines")
    transcript = payload.get("transcript")
    if not lines:
        if not transcript or not isinstance(transcript, list):
            return JsonResponse({"error": "no_transcript_or_lines"}, status=400)
        lines = []
        for x in transcript:
            role = x.get("role"); text = (x.get("text") or "").strip()
            if not text or role not in ("user", "assistant"): continue
            t = re.sub(r'^\s*(user|사용자)\s*:\s*', '', text, flags=re.I)
            t = re.sub(r'^\s*(carepill|케어필)\s*:\s*', '', t, flags=re.I)
            prefix = "User" if role == "user" else "CarePill"
            lines.append(f"{prefix}: {t}")
    SAFE_MAX = 120
    lines = lines[-SAFE_MAX:]

    debug = {"request_id": rid, "lines_count": len(lines), "model": SUMMARIZER_MODEL,
             "openai_status": None, "openai_elapsed_ms": None, "openai_preview": None,
             "saved_path": None, "server_elapsed_ms": None, "exception": None}

    if not lines:
        summary_text = "대화 요약: (비어 있음)"; saved_info=None
        if do_save: saved_info = _save_txt(meta, summary_text, [])
        debug["server_elapsed_ms"] = int((time.time()-t0)*1000)
        out = {"summary_text": summary_text, "saved": bool(saved_info),
               "path": (saved_info or {}).get("path_url") if saved_info else None,
               "download_url": (saved_info or {}).get("download_url") if saved_info else None,
               "file_name": (saved_info or {}).get("file_name") if saved_info else None}
        if debug_mode: out["debug"]=debug
        return JsonResponse(out, status=200)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key: return JsonResponse({"error": "missing_api_key"}, status=500)

    prompt = ("아래는 사용자(User)와 케어필(CarePill)의 대화 로그입니다.\n"
              "핵심만 한국어로 '3줄 요약'을 작성하세요. 각 줄은 1문장으로 간결하게.\n\n"+
              "대화:\n"+"\n".join(lines))

    t1=time.time()
    try:
        resp = requests.post(OPENAI_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": SUMMARIZER_MODEL,
                  "messages":[{"role":"system","content":"너는 한국어 대화 요약 도우미다. 결과는 텍스트(3줄)로만 답한다."},
                              {"role":"user","content": prompt}],
                  "temperature":0.2}, timeout=60)
        debug["openai_status"]=resp.status_code; debug["openai_elapsed_ms"]=int((time.time()-t1)*1000)
        if resp.status_code!=200:
            debug["openai_preview"]=resp.text[:800]; debug["server_elapsed_ms"]=int((time.time()-t0)*1000)
            if debug_mode: _save_debug(rid, debug)
            out={"error":"summarize_failed","detail":f"upstream {resp.status_code}","upstream":resp.text}
            if debug_mode: out["debug"]=debug
            return JsonResponse(out, status=502)
        data=resp.json()
        try: debug["openai_preview"]=json.dumps(data,ensure_ascii=False)[:800]
        except Exception: debug["openai_preview"]=str(data)[:800]
        summary_text=(data["choices"][0]["message"]["content"] or "").strip() or "대화 요약: (생성 실패)"
    except Exception as e:
        debug["exception"]=(traceback.format_exc() or str(e))[-1000:]; debug["server_elapsed_ms"]=int((time.time()-t0)*1000)
        if debug_mode: _save_debug(rid, debug)
        out={"error":"summarize_failed","detail":str(e)}
        if debug_mode: out["debug"]=debug
        return JsonResponse(out, status=502)

    saved_info=None
    if do_save:
        saved_info=_save_txt(meta, summary_text, lines)
        debug["saved_path"]=saved_info["path_url"]
    debug["server_elapsed_ms"]=int((time.time()-t0)*1000)
    if debug_mode: _save_debug(rid, debug)

    out={"summary_text":summary_text, "saved":bool(saved_info),
         "path":(saved_info or {}).get("path_url") if saved_info else None,
         "download_url":(saved_info or {}).get("download_url") if saved_info else None,
         "file_name":(saved_info or {}).get("file_name") if saved_info else None}
    if debug_mode: out["debug"]=debug
    return JsonResponse(out, status=200)

# -----------------------------
# 약봉투 스캔 API (scan.py 이식)
# -----------------------------
# 1) 유틸

def _strip_code_fence(text: str) -> str:
    if not isinstance(text, str): return text
    t = text.strip()
    if t.startswith("```"):
        if t.startswith("```json") or t.startswith("```JSON"):
            t = t.split("\n", 1)[1] if "\n" in t else ""
        else:
            t = t[3:]
        if t.endswith("```"): t = t[:-3]
        t = t.strip()
    return t

# 2) OpenAI 호출(약봉투 전용)

def _call_openai_envelope(image_b64: str, model: str = "gpt-4o-mini") -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key: raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다.")
    text_prompt = (
        "다음 약봉투 이미지를 분석하여 아래 스키마의 정확한 JSON만 출력하세요.\n"
        "가능하면 숫자/날짜는 포맷을 맞추세요.\n"
        "{\n"
        '  "patient_name": "환자명(문자열)",\n'
        '  "age": "나이(숫자 또는 빈 문자열)",\n'
        '  "dispense_date": "조제일자(YYYY-MM-DD 또는 YYYY.MM.DD)",\n'
        '  "pharmacy_name": "약국명",\n'
        '  "prescription_number": "처방전 또는 조제 번호",\n'
        '  "medicine_name": "약품명",\n'
        '  "dosage_instructions": "복용법(예: 아침, 저녁, 취침 전)",\n'
        '  "frequency": "복용횟수/기간(예: 1일 1회 총 30일분)",\n'
        '  "med_features": {\n'
        '    "description": "약의 한줄 설명",\n'
        '    "indications": "어디에 좋은지(적응증)",\n'
        '    "cautions": "주의사항(상호작용/부작용/주의대상 간단 요약)"\n'
        "  }\n"
        "}\n"
        "주의: 오타를 피하고, 사진 속 정보만 사용하세요. 모를 경우 빈 문자열로 두세요. 설명 문장이나 코드펜스 없이 JSON만 출력합니다."
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "너는 한국 약봉투 OCR/정보추출 전문가다. 반드시 유효한 JSON만 출력한다. 사진에 없는 정보는 공란('')으로 남긴다."},
            {"role": "user", "content": [
                {"type": "text", "text": text_prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}", "detail": "high"}}
            ]}
        ],
        "max_tokens": 1000,
        "temperature": 0.1
    }
    r = requests.post("https://api.openai.com/v1/chat/completions",
                      headers={"Authorization": f"Bearer {api_key}", "Content-Type":"application/json"},
                      json=payload, timeout=60)
    if r.status_code!=200:
        raise RuntimeError(f"OpenAI 오류 {r.status_code}: {r.text[:200]}")
    data=r.json(); return data["choices"][0]["message"]["content"]

# 3) 병합 로직
from collections import Counter
from typing import List, Dict, Tuple

def _majority_merge(values: List[str]) -> Tuple[str, float]:
    cleaned = [ (v or "").strip() for v in values if isinstance(v, str) ]
    non_empty = [v for v in cleaned if v]
    if not non_empty: return "", 0.0
    cnt = Counter(non_empty)
    top = cnt.most_common(); top_freq = top[0][1]
    candidates = [v for v,c in top if c==top_freq]
    winner = max(candidates, key=lambda s: len(s))
    conf = cnt[winner] / max(1,len(values))
    return winner, round(conf,3)

def _digits_only(s: str) -> str: return "".join(ch for ch in (s or "") if ch.isdigit())

def _merge_envelope_json(json_list: List[Dict]) -> Tuple[Dict, Dict]:
    fields = ["patient_name","age","dispense_date","pharmacy_name","prescription_number","medicine_name","dosage_instructions","frequency"]
    merged, diag = {}, {}
    results=[]
    for d in json_list:
        res = dict(d or {})
        mf = res.get("med_features", {}) or {}
        res["_mf_description"] = str(mf.get("description", "") or "").strip()
        res["_mf_indications"] = str(mf.get("indications", "") or "").strip()
        res["_mf_cautions"]    = str(mf.get("cautions", "")    or "").strip()
        results.append(res)
    for k in fields:
        vals = [str(r.get(k, "") or "").strip() for r in results]
        if k == "age":
            norm=[_digits_only(v) for v in vals]; best,conf=_majority_merge(norm)
            merged[k]=best; diag[k]={"per_shot":vals,"normalized":norm,"selected":best,"confidence":conf}
        elif k == "prescription_number":
            only=[_digits_only(v) for v in vals]; best_d,conf_d=_majority_merge(only)
            if best_d: merged[k]=best_d; diag[k]={"per_shot":vals,"digits_only":only,"selected":best_d,"confidence":conf_d}
            else: best,conf=_majority_merge(vals); merged[k]=best; diag[k]={"per_shot":vals,"selected":best,"confidence":conf}
        else:
            best,conf=_majority_merge(vals); merged[k]=best; diag[k]={"per_shot":vals,"selected":best,"confidence":conf}
    for subk in ["description","indications","cautions"]:
        key=f"_mf_{subk}"; vals=[r.get(key,"") for r in results]; best,conf=_majority_merge(vals); diag[key] = {"per_shot":vals,"selected":best,"confidence":conf}
    merged["med_features"] = {"description":diag["_mf_description"]["selected"],"indications":diag["_mf_indications"]["selected"],"cautions":diag["_mf_cautions"]["selected"]}
    del diag["_mf_description"]; del diag["_mf_indications"]; del diag["_mf_cautions"]
    return merged, diag

# 4) API 뷰
@csrf_exempt
def api_scan_envelope(request):
    """POST { images: [base64_jpeg_without_prefix, ...] }  (최대 3장)
       또는 multipart 업로드 image=... (단일)
    """
    if request.method != "POST":
        return JsonResponse({"error":"method_not_allowed"}, status=405)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return JsonResponse({"error":"missing_api_key"}, status=500)

    images_b64 = []
    ctype = (request.headers.get('Content-Type') or '').lower()
    try:
        if 'application/json' in ctype:
            payload = json.loads(request.body.decode('utf-8'))
            arr = payload.get('images') or []
            if not isinstance(arr, list): arr=[]
            images_b64 = [str(x or '').strip() for x in arr][:3]
        else:
            # multipart/form-data 폴백: 단일 파일
            f = request.FILES.get('image')
            if not f: return JsonResponse({"error":"no_image"}, status=400)
            images_b64 = [ (f.read()).decode('latin1') ]  # 고정X: 아래서 정상화
    except Exception as e:
        return JsonResponse({"error":"bad_payload","detail":str(e)}, status=400)

    if not images_b64:
        return JsonResponse({"error":"no_images"}, status=400)

    shots_raw=[]; json_list=[]
    for idx,b64 in enumerate(images_b64,1):
        # dataURL 제거 방어
        b64 = re.sub(r'^data:image\/(png|jpeg);base64,', '', b64, flags=re.I)
        try:
            raw = _call_openai_envelope(b64)
            cleaned = _strip_code_fence(raw)
            try:
                parsed = json.loads(cleaned)
            except Exception:
                parsed = {}
            shots_raw.append({"index": idx, "raw": cleaned, "json": parsed, "image_path": f"client_shot_{idx}"})
            json_list.append(parsed)
        except Exception as e:
            shots_raw.append({"index": idx, "raw": f"ERROR: {e}", "json": {}, "image_path": None})
            json_list.append({})

    merged, diag = _merge_envelope_json(json_list)

    out = {"analysis_type":"envelope", "shots": shots_raw, "merged": merged, "diagnostics": diag}
    return JsonResponse(out, status=200)
