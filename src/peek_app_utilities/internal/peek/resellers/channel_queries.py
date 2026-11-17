"""Raw Peek GraphQL query and response shape for reseller channels. Internal.

Channels themselves are returned in full; ``$first`` limits the number of
agents fetched per channel.
"""

from __future__ import annotations

from typing import Final, TypedDict

CHANNELS_QUERY: Final = """
  query Sales($first: Int) {
    channels {
      id
      agents(first: $first) {
        edges {
          node {
            email
            name
            internalNotes
            phone
          }
        }
      }
      name
      notes
      state
      type
      pricingModel
    }
  }
"""
"""Fetches reseller channels with up to ``$first`` agents each."""


class AgentNode(TypedDict, total=False):
    """A single agent node."""

    email: str | None
    name: str
    internalNotes: str | None
    phone: str | None


class AgentEdge(TypedDict, total=False):
    node: AgentNode


class AgentsConnection(TypedDict, total=False):
    edges: list[AgentEdge] | None


class ChannelNode(TypedDict, total=False):
    """A single channel node as returned by :data:`CHANNELS_QUERY`."""

    id: str
    name: str
    notes: str | None
    pricingModel: str
    state: str
    type: str
    agents: AgentsConnection | None


class ChannelsResponse(TypedDict, total=False):
    """The ``data`` payload of :data:`CHANNELS_QUERY`."""

    channels: list[ChannelNode] | None
