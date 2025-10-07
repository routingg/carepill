from django.shortcuts import render

def home(request):
    return render(request, "carepill/home.html")

def scan(request):
    return render(request, "carepill/scan.html")

def meds(request):
    return render(request, "carepill/meds.html")

def voice(request):
    return render(request, "carepill/voice.html")



# carepill/views.py
import os, json, requests
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
@csrf_exempt
@require_http_methods(["POST"])
def realtime_session(request):
    """
    OpenAI Realtime용 ephemeral client secret 발급 (project key 호환 버전)
    """
    import json, os, requests

    api_key = os.environ.get("OPENAI_API_KEY")  # sk-proj 키 사용 가능
    if not api_key:
        return HttpResponseBadRequest("OPENAI_API_KEY is not set")

    url = "https://api.openai.com/v1/realtime/client_secrets"

    payload = {
        "session": {
            "type": "realtime",
            "model": "gpt-4o-realtime-preview",
            # 필요하면 옵션 추가 가능:
            # "voice": "verse",
            # "input_audio_format": "pcm16",
            # "output_audio_format": "pcm16",
            # "instructions": "당신은 케어필이라는 약 도우미입니다.",
        }
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=20)
        print("🔁 Status:", r.status_code)
        print("📦 Response:", r.text[:200])
        return JsonResponse(r.json(), status=r.status_code, safe=False)
    except requests.RequestException as e:
        return JsonResponse({"error": str(e)}, status=502)
