from rest_framework.routers import DefaultRouter

from apps.permissions.views import PermissionViewSet, RoleAssignmentViewSet, RoleViewSet

router = DefaultRouter()
router.register("permissions", PermissionViewSet, basename="permission")
router.register("roles", RoleViewSet, basename="role")
router.register("role-assignments", RoleAssignmentViewSet, basename="role-assignment")

urlpatterns = router.urls
