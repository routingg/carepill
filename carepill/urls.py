from django.urls import path
from .view_speech import voice_stream_view
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("scan/", views.scan, name="scan"),
    path("meds/", views.meds, name="meds"),
    path("voice/", views.voice, name="voice"),
    
    path("voice-stream/", voice_stream_view, name="voice_stream"),

    
]
