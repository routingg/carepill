from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("scan/", views.scan, name="scan"),
    path("meds/", views.meds, name="meds"),
    path("voice/", views.voice, name="voice"),

    # WebRTC용 에페메럴 세션 토큰 발급 (클라 직결)
    path("api/realtime/session/", views.issue_ephemeral, name="rt_ephemeral"),
    path("api/realtime/sdp-exchange/", views.realtime_sdp_exchange, name="rt_sdp_exchange"),


    path("api/conversation/summarize_and_save/", views.api_conversation_summarize_and_save, name="api_conversation_summarize_and_save"),
    path("api/conversation/download/", views.api_conversation_download),
    
    ]
