from rest_framework.routers import DefaultRouter

from apps.snapshots.views import SnapshotViewSet

router = DefaultRouter()
router.register("snapshots", SnapshotViewSet, basename="snapshot")

urlpatterns = router.urls
