from rest_framework.routers import DefaultRouter

from apps.vm_templates.views import TemplateViewSet

router = DefaultRouter()
router.register("templates", TemplateViewSet, basename="template")

urlpatterns = router.urls
