"""Reseller-channel operations against the Peek backoffice API.

Obtain an instance via ``PeekAccessService.get_reseller_service()``.
"""

from __future__ import annotations

from typing import Final

from peek_app_utilities.internal.peek.gateway_endpoints import SALES_ENDPOINT
from peek_app_utilities.internal.peek.graphql_client import GraphQLClient
from peek_app_utilities.internal.peek.resellers.channel_converter import from_channels_response
from peek_app_utilities.internal.peek.resellers.channel_queries import CHANNELS_QUERY
from peek_app_utilities.models.peek.channel import Channel

DEFAULT_AGENTS_PER_CHANNEL: Final = 10
"""Default number of agents fetched per channel."""


class ResellerService:
    def __init__(self, client: GraphQLClient) -> None:
        self._client = client

    async def get_all_channels(self, agents_per_channel: int | None = None) -> list[Channel]:
        """Returns all reseller channels, each with up to ``agents_per_channel``
        agents (default 10)."""
        first = DEFAULT_AGENTS_PER_CHANNEL if agents_per_channel is None else agents_per_channel
        body = await self._client.request(SALES_ENDPOINT, CHANNELS_QUERY, {"first": first})
        return from_channels_response(body.get("data"))
