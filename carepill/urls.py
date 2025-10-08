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
]
