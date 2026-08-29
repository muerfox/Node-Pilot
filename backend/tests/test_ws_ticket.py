import pytest
from django.contrib.auth.models import AnonymousUser
from rest_framework.test import APIClient

from apps.authentication.ws_auth import _user_from_ticket
from apps.authentication.ws_ticket import issue_ticket, redeem_ticket

pytestmark = pytest.mark.django_db


def test_redeem_returns_the_issuing_users_uuid(user):
    ticket = issue_ticket(user)
    assert redeem_ticket(ticket) == str(user.uuid)


def test_ticket_is_single_use(user):
    ticket = issue_ticket(user)
    assert redeem_ticket(ticket) == str(user.uuid)
    assert redeem_ticket(ticket) is None  # second redemption fails


def test_unknown_ticket_is_rejected():
    assert redeem_ticket("not-a-real-ticket") is None


def test_ws_ticket_endpoint_requires_authentication():
    client = APIClient()
    response = client.post("/api/v1/auth/ws-ticket/")
    assert response.status_code == 401


def test_ws_ticket_endpoint_issues_a_redeemable_ticket(user):
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post("/api/v1/auth/ws-ticket/")

    assert response.status_code == 200
    ticket = response.data["ticket"]
    assert redeem_ticket(ticket) == str(user.uuid)


# These three hit the DB from inside `database_sync_to_async`, which runs
# in a real separate thread -- under SQLite that needs a genuinely
# committed (not test-transaction-wrapped) row to see across threads
# without deadlocking on the file lock, hence `transaction=True` instead
# of the module-level `django_db`.


@pytest.mark.django_db(transaction=True)
async def test_ws_middleware_resolves_the_correct_user_from_a_valid_ticket(user):
    ticket = issue_ticket(user)
    resolved = await _user_from_ticket(ticket)
    assert resolved.pk == user.pk


async def test_ws_middleware_resolves_anonymous_for_an_invalid_ticket():
    resolved = await _user_from_ticket("garbage")
    assert isinstance(resolved, AnonymousUser)


@pytest.mark.django_db(transaction=True)
async def test_ws_middleware_resolves_anonymous_after_ticket_already_redeemed(user):
    ticket = issue_ticket(user)
    await _user_from_ticket(ticket)  # first (legitimate) connection
    resolved = await _user_from_ticket(ticket)  # replay attempt
    assert isinstance(resolved, AnonymousUser)
