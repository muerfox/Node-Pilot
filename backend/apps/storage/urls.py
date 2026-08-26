from rest_framework.routers import DefaultRouter

from apps.storage.views import StoragePoolViewSet

router = DefaultRouter()
router.register("storages", StoragePoolViewSet, basename="storage-pool")

urlpatterns = router.urls
