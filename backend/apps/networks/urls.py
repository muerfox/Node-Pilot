from rest_framework.routers import DefaultRouter

from apps.networks.views import IPAddressViewSet, IPPoolViewSet, NetworkViewSet, SubnetViewSet

router = DefaultRouter()
router.register("networks", NetworkViewSet, basename="network")
router.register("subnets", SubnetViewSet, basename="subnet")
router.register("ip-pools", IPPoolViewSet, basename="ip-pool")
router.register("ips", IPAddressViewSet, basename="ip-address")

urlpatterns = router.urls
