"""Custom-question operations against the Peek backoffice API.

Obtain an instance via ``PeekAccessService.get_custom_question_service()`` rather
than constructing it directly — the access service wires in the authenticated,
shared transport.
"""

from __future__ import annotations

from peek_app_utilities.internal.peek.custom_questions.custom_question_converter import (
    from_question_nodes,
)
from peek_app_utilities.internal.peek.custom_questions.custom_question_queries import (
    ALL_CUSTOM_QUESTIONS_QUERY,
)
from peek_app_utilities.internal.peek.gateway_endpoints import SALES_ENDPOINT
from peek_app_utilities.internal.peek.graphql_client import GraphQLClient
from peek_app_utilities.models.peek.custom_question import CustomQuestion


class CustomQuestionService:
    """Reads custom questions defined on the account. Obtain via
    ``PeekAccessService.get_custom_question_service()``."""

    def __init__(self, client: GraphQLClient) -> None:
        self._client = client

    async def get_all(self) -> list[CustomQuestion]:
        """Returns every custom question defined on the account, across all
        activities. Choice-style questions (``SELECT_ONE``, ``LOCATION``, …) carry
        their selectable :attr:`CustomQuestion.options`; free-text/checkbox
        questions return an empty option list.

        These are account-wide question **definitions**, not customer answers — no
        PII is involved, so the result is unaffected by ``full_customer_access``.
        Unlike ``ProductService.get_custom_questions``, the catalog carries no
        per-activity configuration, so ``order`` is ``0`` and ``is_required`` is
        ``False`` on every entry.

        :returns: Every custom question on the account, or ``[]`` when none exist.

        Example::

            questions = await peek.get_custom_question_service().get_all()
        """
        body = await self._client.request(SALES_ENDPOINT, ALL_CUSTOM_QUESTIONS_QUERY, {})
        return from_question_nodes((body.get("data") or {}).get("questions") or [])
