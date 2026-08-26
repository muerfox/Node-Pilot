from rest_framework.routers import DefaultRouter

from apps.virtual_machines.views import VirtualMachineViewSet

router = DefaultRouter()
router.register("vms", VirtualMachineViewSet, basename="vm")

urlpatterns = router.urls
