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
