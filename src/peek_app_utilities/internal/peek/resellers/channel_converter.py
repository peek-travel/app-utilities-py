"""Pure functions mapping raw channel nodes into the clean :class:`Channel`
model, flattening the agents edge/node structure.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from peek_app_utilities.internal.peek.resellers.channel_queries import AgentNode, ChannelNode
from peek_app_utilities.models.peek.channel import Agent, Channel


def from_channels_response(response: Mapping[str, Any] | None) -> list[Channel]:
    """Converts a channels response into :class:`Channel` models."""
    channels: list[ChannelNode] = (response or {}).get("channels") or []
    return [_from_channel_node(node) for node in channels]


def _from_channel_node(node: ChannelNode) -> Channel:
    edges = (node.get("agents") or {}).get("edges") or []
    return Channel(
        id=node.get("id") or "",
        name=node.get("name") or "",
        notes=node.get("notes"),
        pricing_model=node.get("pricingModel") or "",
        state=node.get("state") or "",
        type=node.get("type") or "",
        agents=[_from_agent_node(edge.get("node") or {}) for edge in edges],
    )


def _from_agent_node(node: AgentNode) -> Agent:
    return Agent(
        email=node.get("email"),
        name=node.get("name") or "",
        internal_notes=node.get("internalNotes"),
        phone=node.get("phone"),
    )
