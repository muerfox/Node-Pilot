import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

import django  # noqa: E402

django.setup()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from django.core.asgi import get_asgi_application  # noqa: E402

from apps.api.routing import websocket_urlpatterns  # noqa: E402
from apps.authentication.ws_auth import TicketAuthMiddlewareStack  # noqa: E402

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        # Ticket-based (not session-cookie-based, not a raw JWT in the URL
        # either) -- see apps.authentication.ws_auth / ws_ticket for why.
        "websocket": TicketAuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
    }
)
