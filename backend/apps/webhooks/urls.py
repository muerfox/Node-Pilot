from rest_framework.routers import DefaultRouter

from apps.webhooks.views import WebhookViewSet

router = DefaultRouter()
router.register("webhooks", WebhookViewSet, basename="webhook")

urlpatterns = router.urls
