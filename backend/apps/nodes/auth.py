from __future__ import annotations

from rest_framework import authentication, exceptions

from apps.nodes.models import Agent, AgentStatus


class AgentTokenAuthentication(authentication.BaseAuthentication):
    """
    Authenticates NodePilot Agent processes (not human users) via
    `Authorization: Agent <raw-token>`. Sets request.agent; request.user is
    left as AnonymousUser since agents are not Django users.
    """

    keyword = "Agent"

    def authenticate(self, request):
        auth_header = authentication.get_authorization_header(request).split()
        if not auth_header or auth_header[0].decode() != self.keyword:
            return None
        if len(auth_header) != 2:
            raise exceptions.AuthenticationFailed("Invalid agent token header.")

        raw_token = auth_header[1].decode()
        token_hash = Agent.hash_token(raw_token)
        try:
            agent = Agent.objects.select_related("node", "node__organization").get(token_hash=token_hash)
        except Agent.DoesNotExist as exc:
            raise exceptions.AuthenticationFailed("Invalid agent token.") from exc

        if agent.status not in (AgentStatus.ACTIVE,):
            raise exceptions.AuthenticationFailed(f"Agent is {agent.status} and may not connect.")

        from django.contrib.auth.models import AnonymousUser

        request.agent = agent
        return (AnonymousUser(), agent)
