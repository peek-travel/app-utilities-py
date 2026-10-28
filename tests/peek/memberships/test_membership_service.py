import pytest

from peek_app_utilities.internal.peek.memberships.membership_service import MembershipService
from peek_app_utilities.models.peek.membership import (
    Membership,
    MembershipPurchaseInput,
    PurchasedMembership,
)

VALID_PURCHASE = MembershipPurchaseInput(membership_variant_id="mv-1", email="ada@example.com")

QUOTE_OK = {"createQuoteV2": {"errors": None, "quote": {"id": "q-1"}}}


def order_ok(sales: list) -> dict:
    return {"createOrderFromQuote": {"errors": None, "order": {"id": "o_1", "sales": sales}}}


# ─── get_all ──────────────────────────────────────────────────────────────────


async def test_get_all_flattens_membership_variants_from_the_response(gql):
    gql.queue(
        {
            "memberships": [
                {
                    "id": "m1",
                    "name": "Gold",
                    "membershipVariants": [
                        {
                            "id": "v1",
                            "description": None,
                            "imageUrl": None,
                            "externalName": "Gold",
                            "internalName": "gold",
                        }
                    ],
                }
            ]
        }
    )

    memberships = await MembershipService(gql).get_all()

    assert memberships == [
        Membership(
            id="m1",
            membership_variant_id="v1",
            description=None,
            external_name="Gold",
            image_url=None,
            internal_name="gold",
            display_name="Gold",
        )
    ]
    assert gql.calls[0].endpoint_name == "sales"
    assert gql.calls[0].variables == {}
    assert "memberships {" in gql.calls[0].query


async def test_get_all_returns_an_empty_list_when_a_200_response_carries_no_data(gql):
    gql.queue_body({})
    assert await MembershipService(gql).get_all() == []


# ─── purchase ─────────────────────────────────────────────────────────────────


async def test_purchase_runs_the_quote_then_order_flow_and_returns_the_membership(gql):
    gql.queue(QUOTE_OK).queue(
        order_ok(
            [
                {
                    "id": "mem-1",
                    "displayId": "M-1",
                    "primaryMember": {"id": "pm-1", "name": "Ada"},
                    "balance": {
                        "total": {"amount": "0.00", "currency": "USD", "formatted": "$0.00"}
                    },
                }
            ]
        )
    )

    result = await MembershipService(gql).purchase(
        MembershipPurchaseInput(
            membership_variant_id="mv-1",
            email="ada@example.com",
            country="US",
            phone="+1 555-1234",
            name="Ada",
            formatted_address="1 Main St",
            membership_code="GOLD",
        )
    )

    assert result == PurchasedMembership(
        order_id="o_1",
        membership_id="mem-1",
        display_id="M-1",
        primary_member_id="pm-1",
        primary_member_name="Ada",
        balance_amount="0.00",
        balance_currency="USD",
        balance_formatted="$0.00",
    )

    quote_call, order_call = gql.calls
    assert "createQuoteV2" in quote_call.query
    quote = quote_call.variables["input"]["quoteInput"]["membershipQuotes"][0]
    assert quote["membershipVariantId"] == "mv-1"
    assert quote["status"] == "CONFIRMED"
    assert isinstance(quote["refid"], str) and quote["refid"]
    assert quote["member"] == {
        "email": "ada@example.com",
        "country": "US",
        "formattedAddress": "1 Main St",
        "membershipCode": "GOLD",
        "name": "Ada",
        "phone": "+1 555-1234",
    }
    assert "createOrderFromQuote" in order_call.query
    assert order_call.variables["input"] == {"quoteId": "q-1"}


async def test_purchase_omits_blank_optional_member_fields(gql):
    gql.queue(QUOTE_OK).queue(order_ok([{"id": "m", "displayId": "M"}]))

    await MembershipService(gql).purchase(
        MembershipPurchaseInput(
            membership_variant_id="mv-1",
            email="ada@example.com",
            country=None,
            formatted_address="",
            membership_code=" ",
            name="  ",
            phone=None,
        )
    )

    quote = gql.calls[0].variables["input"]["quoteInput"]["membershipQuotes"][0]
    assert quote["member"] == {"email": "ada@example.com"}


async def test_purchase_defaults_the_balance_when_missing(gql):
    gql.queue(QUOTE_OK).queue(order_ok([{"id": "m", "displayId": "M"}]))

    result = await MembershipService(gql).purchase(VALID_PURCHASE)

    assert result.primary_member_id is None
    assert result.primary_member_name is None
    assert result.balance_amount == "0.00"
    assert result.balance_currency == "USD"
    assert result.balance_formatted == "$0.00"


async def test_purchase_raises_when_the_quote_has_errors(gql):
    gql.queue(
        {
            "createQuoteV2": {
                "errors": [{"code": "X", "detail": "bad variant", "value": None}],
                "quote": None,
            }
        }
    )
    with pytest.raises(ValueError, match="quote: bad variant"):
        await MembershipService(gql).purchase(VALID_PURCHASE)
    assert len(gql.calls) == 1


async def test_purchase_raises_when_the_quote_id_is_missing(gql):
    gql.queue({"createQuoteV2": {"errors": None, "quote": None}})
    with pytest.raises(ValueError, match="missing quote id"):
        await MembershipService(gql).purchase(VALID_PURCHASE)


async def test_purchase_raises_when_the_quote_payload_is_absent(gql):
    gql.queue_body({})
    with pytest.raises(ValueError, match="missing quote id"):
        await MembershipService(gql).purchase(VALID_PURCHASE)


async def test_purchase_raises_when_the_order_has_errors(gql):
    gql.queue(QUOTE_OK).queue(
        {
            "createOrderFromQuote": {
                "errors": [{"code": "X", "detail": "declined", "value": None}],
                "order": None,
            }
        }
    )
    with pytest.raises(ValueError, match="order: declined"):
        await MembershipService(gql).purchase(VALID_PURCHASE)


async def test_purchase_raises_when_the_order_has_no_sales(gql):
    gql.queue(QUOTE_OK).queue(order_ok([]))
    with pytest.raises(ValueError, match="no sales found"):
        await MembershipService(gql).purchase(VALID_PURCHASE)


async def test_purchase_raises_when_the_order_is_missing(gql):
    gql.queue(QUOTE_OK).queue({"createOrderFromQuote": {"errors": None, "order": None}})
    with pytest.raises(ValueError, match="no sales found"):
        await MembershipService(gql).purchase(VALID_PURCHASE)


@pytest.mark.parametrize(
    ("input", "pattern"),
    [
        (
            MembershipPurchaseInput(membership_variant_id="", email="a@b.co"),
            "membershipVariantId is required",
        ),
        (MembershipPurchaseInput(membership_variant_id="mv", email=""), "email is required"),
        (MembershipPurchaseInput(membership_variant_id="mv", email="bad"), "email is invalid"),
        (
            MembershipPurchaseInput(membership_variant_id="mv", email="a@b.co", country="USA"),
            "country is invalid",
        ),
        (
            MembershipPurchaseInput(membership_variant_id="mv", email="a@b.co", phone="abc!"),
            "phone is invalid",
        ),
    ],
)
async def test_purchase_rejects_invalid_input(gql, input, pattern):
    with pytest.raises(ValueError, match=pattern):
        await MembershipService(gql).purchase(input)
    assert gql.calls == []


async def test_purchase_joins_every_validation_error_into_one_message(gql):
    with pytest.raises(ValueError) as excinfo:
        await MembershipService(gql).purchase(
            MembershipPurchaseInput(membership_variant_id=" ", email="  ", country="usa")
        )
    assert str(excinfo.value) == (
        "membershipVariantId is required, email is required, country is invalid"
    )
