from django.urls import path

from apps.api.health import LivenessView, ReadinessView

urlpatterns = [
    path("live/", LivenessView.as_view(), name="health-live"),
    path("ready/", ReadinessView.as_view(), name="health-ready"),
]
