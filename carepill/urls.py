from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("scan/", views.scan, name="scan"),
    path("meds/", views.meds, name="meds"),
    path("voice/", views.voice, name="voice"),
]
