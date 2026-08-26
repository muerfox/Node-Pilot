from rest_framework.routers import DefaultRouter

from apps.authentication.views import APITokenViewSet, LoginView, RefreshView
from django.urls import path

router = DefaultRouter()
router.register("auth/tokens", APITokenViewSet, basename="api-token")

urlpatterns = [
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/refresh/", RefreshView.as_view(), name="auth-refresh"),
] + router.urls
