from rest_framework.routers import DefaultRouter

from apps.organizations.views import MembershipViewSet, OrganizationViewSet, ProjectViewSet, QuotaViewSet

router = DefaultRouter()
router.register("organizations", OrganizationViewSet, basename="organization")
router.register("projects", ProjectViewSet, basename="project")
router.register("memberships", MembershipViewSet, basename="membership")
router.register("quotas", QuotaViewSet, basename="quota")

urlpatterns = router.urls
