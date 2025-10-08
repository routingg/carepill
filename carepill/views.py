from django.shortcuts import render

def home(request):
    return render(request, "carepill/home.html")

def scan(request):
    return render(request, "carepill/scan.html")

def meds(request):
    return render(request, "carepill/meds.html")

def voice(request):
    return render(request, "carepill/voice.html")


