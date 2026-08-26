from rest_framework.routers import DefaultRouter

from apps.backups.views import BackupScheduleViewSet, BackupTargetViewSet, BackupViewSet

router = DefaultRouter()
router.register("backup-targets", BackupTargetViewSet, basename="backup-target")
router.register("backup-schedules", BackupScheduleViewSet, basename="backup-schedule")
router.register("backups", BackupViewSet, basename="backup")

urlpatterns = router.urls
