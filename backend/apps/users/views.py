from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.users.models import User
from apps.users.serializers import UserCreateSerializer, UserSerializer


class UserViewSet(ModelViewSet):
    """
    /api/v1/users/ -- platform-wide user administration. Unlike every other
    resource in the API, users aren't scoped to a single Organization (a
    user can belong to several), so the org-scoped RBAC policy doesn't
    apply cleanly here: user.view/user.manage are platform-admin
    capabilities, gated on Django's `is_staff`/`is_superuser` rather than
    a per-organization RoleAssignment. Per-organization membership and
    role grants are managed separately via apps.organizations (Membership)
    and apps.permissions (RoleAssignment), which *are* org-scoped.
    A user may always retrieve their own profile via /users/me/.
    """

    queryset = User.objects.all().order_by("username")
    lookup_field = "uuid"
    search_fields = ["username", "email", "first_name", "last_name"]
    filterset_fields = ["is_active", "is_service_account"]

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        return UserSerializer

    def get_permissions(self):
        if self.action in ("me", "lookup"):
            return [IsAuthenticated()]
        return [IsAuthenticated(), IsAdminUser()]

    def get_object(self):
        if self.action == "me":
            return self.request.user
        return super().get_object()

    @action(detail=False, methods=["get"])
    def me(self, request):
        return Response(UserSerializer(request.user).data)

    @action(detail=False, methods=["get"])
    def lookup(self, request):
        """
        GET /users/lookup/?username=<exact> -- open to any authenticated
        user (not just staff), unlike list/retrieve/create, so an org
        admin adding a Membership or RoleAssignment can resolve a
        username to a uuid without needing platform-wide user.view.
        Exact match only (no partial `search`), so this can't be used to
        enumerate/browse the user list -- it only confirms a username you
        already know resolves to an account, the same information a login
        form already reveals.
        """
        username = request.query_params.get("username", "").strip()
        if not username:
            return Response({"error": {"code": "VALIDATION_FAILED", "message": "username is required", "details": {}}}, status=400)
        user = User.objects.filter(username=username, is_active=True).first()
        if user is None:
            return Response({"error": {"code": "NOT_FOUND", "message": "No active user with that username.", "details": {}}}, status=404)
        return Response({"uuid": str(user.uuid), "username": user.username})
