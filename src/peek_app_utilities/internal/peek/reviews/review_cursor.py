"""Encode/decode for the Peek reviews connection cursor. Internal.

A cursor is the base64 of ``range:<start>..<end>,<offset>`` where ``<offset>``
is the **absolute index** of the object in the current result set.
:func:`encode_cursor` mints the ``after`` cursor used to skip a fixed number of
the newest reviews.
"""

from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass
from typing import Final

_CURSOR_REGEX: Final = re.compile(r"^range:(\d+)\.\.(\d+),(\d+)$")
_ERROR_UNRECOGNIZED_CURSOR: Final = "Unrecognized review cursor: "


@dataclass(frozen=True, slots=True, kw_only=True)
class DecodedCursor:
    """The parsed parts of a reviews cursor."""

    start: int
    """Inclusive start index of the page window the object belonged to."""
    end: int
    """Inclusive end index of the page window the object belonged to."""
    offset: int
    """Absolute index of the object in the result set."""


def decode_cursor(cursor: str) -> DecodedCursor:
    """Decodes a base64 reviews cursor into its parts.

    :raises ValueError: when the cursor is not a base64 ``range:…`` token.
    """
    try:
        text = base64.b64decode(cursor).decode("utf-8", errors="replace")
    except (binascii.Error, ValueError):
        text = ""
    match = _CURSOR_REGEX.match(text)
    if match is None:
        raise ValueError(f"{_ERROR_UNRECOGNIZED_CURSOR}{cursor}")
    start, end, offset = match.groups()
    return DecodedCursor(start=int(start), end=int(end), offset=int(offset))


def decode_offset(cursor: str) -> int:
    """Returns just the absolute offset encoded in a cursor."""
    return decode_cursor(cursor).offset


def encode_cursor(offset: int, page_size: int) -> str:
    """Rebuilds a cursor that points at a given absolute ``offset``, mimicking the
    last edge of a ``page_size`` page that ends at ``offset``. Used to resume
    (``after``) pagination from a cached, re-anchored offset. The API resolves
    the next window from the trailing offset."""
    start = max(0, offset - page_size + 1)
    return base64.b64encode(f"range:{start}..{offset},{offset}".encode()).decode("ascii")
