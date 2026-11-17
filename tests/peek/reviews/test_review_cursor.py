import pytest

from peek_app_utilities.internal.peek.reviews.review_cursor import (
    DecodedCursor,
    decode_cursor,
    decode_offset,
    encode_cursor,
)

# ─── decode_cursor ───────────────────────────────────────────────────────────


def test_decodes_the_documented_gateway_cursors():
    # From the reply sample: range:0..49,0 / 1 / 2.
    assert decode_cursor("cmFuZ2U6MC4uNDksMA==") == DecodedCursor(start=0, end=49, offset=0)
    assert decode_cursor("cmFuZ2U6MC4uNDksMQ==").offset == 1
    assert decode_cursor("cmFuZ2U6MC4uNDksMg==").offset == 2
    # From the variables sample: range:50..99,50.
    assert decode_cursor("cmFuZ2U6NTAuLjk5LDUw") == DecodedCursor(start=50, end=99, offset=50)


def test_raises_on_a_cursor_that_is_not_a_base64_range_token():
    with pytest.raises(ValueError, match="Unrecognized review cursor"):
        decode_cursor("bm90LWEtY3Vyc29y")


def test_raises_on_a_cursor_that_is_not_valid_base64():
    with pytest.raises(ValueError, match="Unrecognized review cursor"):
        decode_cursor("!!!not base64!!!")


# ─── encode_cursor ───────────────────────────────────────────────────────────


def test_round_trips_an_offset_through_decode_offset():
    assert decode_offset(encode_cursor(123, 50)) == 123


def test_mimics_the_last_edge_of_a_page_that_ends_at_the_offset():
    # A 50-item page ending at offset 99 spans range 50..99.
    assert decode_cursor(encode_cursor(99, 50)) == DecodedCursor(start=50, end=99, offset=99)


def test_clamps_the_page_start_at_zero_for_shallow_offsets():
    assert decode_cursor(encode_cursor(10, 50)) == DecodedCursor(start=0, end=10, offset=10)


def test_encodes_the_documented_range_format():
    # range:50..99,50
    assert encode_cursor(50, 1) == "cmFuZ2U6NTAuLjUwLDUw"
    assert encode_cursor(99, 50) == "cmFuZ2U6NTAuLjk5LDk5"
