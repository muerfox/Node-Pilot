from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.audit.services import log_from_request
from apps.authentication.models import APIToken
from apps.authentication.serializers import APITokenCreateSerializer, APITokenSerializer
from apps.authentication.ws_ticket import TICKET_TTL_SECONDS, issue_ticket


class LoginView(TokenObtainPairView):
    """POST username/password -> JWT access + refresh tokens (section 32)."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"


class RefreshView(TokenRefreshView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"


class WSTicketView(APIView):
    """
    POST /api/v1/auth/ws-ticket/ -- exchanges the caller's existing
    authenticated session (JWT or API token, checked via the normal
    Authorization header) for a short-lived, single-use ticket suitable
    for putting in a WebSocket URL. See apps.authentication.ws_ticket.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        return Response({"ticket": issue_ticket(request.user), "expires_in": TICKET_TTL_SECONDS})


class APITokenViewSet(ModelViewSet):
    """
    /api/v1/auth/tokens/ -- a user manages their own API tokens. The raw
    secret is only ever present in the create response.
    """

    permission_classes = [IsAuthenticated]
    lookup_field = "uuid"
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "token_create"

    def get_queryset(self):
        return APIToken.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.action == "create":
            return APITokenCreateSerializer
        return APITokenSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        raw_token, token_hash, prefix = APIToken.generate()
        token = APIToken.objects.create(
            user=request.user,
            token_hash=token_hash,
            prefix=prefix,
            **serializer.validated_data,
        )
        log_from_request(request, action="API_TOKEN_CREATE", resource_type="APIToken", resource_id=str(token.uuid))
        data = APITokenSerializer(token).data
        data["token"] = raw_token
        return Response(data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        token = self.get_object()
        token.revoke()
        log_from_request(request, action="API_TOKEN_REVOKE", resource_type="APIToken", resource_id=str(token.uuid))
        return Response(status=status.HTTP_204_NO_CONTENT)
