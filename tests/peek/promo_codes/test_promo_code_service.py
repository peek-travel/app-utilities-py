from dataclasses import replace

import pytest

from peek_app_utilities.internal.peek.promo_codes.promo_code_service import (
    PromoCodeService,
    PromoCodeServiceOptions,
)
from peek_app_utilities.models.peek.promo_code import (
    CreatedPromoCode,
    CreatePromoCodeInput,
    PromoCode,
    PromoCodeFixedAmount,
)


def promo_code_node(id: str) -> dict:
    return {
        "id": id,
        "name": f"Code {id}",
        "percentAmount": 10,
        "perTicketDiscount": False,
        "redemptionCode": id.upper(),
        "fixedAmount": None,
    }


VALID_INPUT = CreatePromoCodeInput(
    name="Summer", code="SUMMER", amount="10", discount_type="percent"
)


# ─── get_all ──────────────────────────────────────────────────────────────────


async def test_get_all_paginates_across_pages(gql):
    gql.queue(
        {
            "promoCodes": {
                "edges": [{"node": promo_code_node("p1")}],
                "pageInfo": {"hasNextPage": True, "endCursor": "c1"},
            }
        }
    ).queue(
        {
            "promoCodes": {
                "edges": [{"node": promo_code_node("p2")}],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }
        }
    )

    codes = await PromoCodeService(gql).get_all()

    assert [c.id for c in codes] == ["p1", "p2"]
    assert codes[0] == PromoCode(
        id="p1",
        name="Code p1",
        percent_amount=10,
        per_ticket_discount=False,
        redemption_code="P1",
        fixed_amount=None,
    )
    assert gql.calls[0].variables == {"first": 50, "after": None}
    assert gql.calls[1].variables == {"first": 50, "after": "c1"}
    assert gql.calls[0].endpoint_name == "sales"


async def test_get_all_returns_an_empty_list_when_a_200_response_carries_no_data_honoring_page_size(
    gql,
):
    gql.queue_body({})

    codes = await PromoCodeService(gql, PromoCodeServiceOptions(page_size=5)).get_all()

    assert codes == []
    assert gql.calls[0].variables["first"] == 5


async def test_get_all_maps_a_fixed_amount_code(gql):
    gql.queue(
        {
            "promoCodes": {
                "edges": [
                    {
                        "node": {
                            "id": "p3",
                            "name": "Flat",
                            "percentAmount": None,
                            "perTicketDiscount": True,
                            "redemptionCode": "FLAT",
                            "fixedAmount": {"amount": 10, "currency": "USD", "formatted": "$10.00"},
                        }
                    },
                    {"node": None},
                ],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }
        }
    )

    codes = await PromoCodeService(gql, PromoCodeServiceOptions()).get_all()

    assert codes[0] == PromoCode(
        id="p3",
        name="Flat",
        percent_amount=None,
        per_ticket_discount=True,
        redemption_code="FLAT",
        fixed_amount=PromoCodeFixedAmount(amount=10.0, currency="USD", formatted="$10.00"),
    )
    assert codes[1].id == ""
    assert gql.calls[0].variables["first"] == 50


# ─── create ───────────────────────────────────────────────────────────────────


async def test_create_maps_a_percent_discount_and_returns_the_created_id_name(gql):
    gql.queue({"createPromoCode": {"id": "p1", "name": "Summer"}})

    result = await PromoCodeService(gql).create(replace(VALID_INPUT, max_redemptions=100))

    assert result == CreatedPromoCode(id="p1", name="Summer")
    assert gql.calls[0].variables["input"] == {
        "code": "SUMMER",
        "name": "Summer",
        "maxRedeemCount": 100,
        "percentAmount": "10",
    }
    assert "mutation Sales($input: CreatePromoCodeInput!)" in gql.calls[0].query


async def test_create_maps_a_fixed_discount_with_default_usd_currency(gql):
    gql.queue({"createPromoCode": {"id": "p2", "name": "Flat"}})

    await PromoCodeService(gql).create(
        CreatePromoCodeInput(name="Flat", code="FLAT", amount="5", discount_type="fixed")
    )

    input = gql.calls[0].variables["input"]
    assert input["fixedAmount"] == {"amount": "5", "currency": "USD"}
    assert "maxRedeemCount" not in input
    assert "percentAmount" not in input


async def test_create_honors_an_explicit_currency(gql):
    gql.queue({"createPromoCode": {"id": "p2", "name": "Flat"}})

    await PromoCodeService(gql).create(
        CreatePromoCodeInput(
            name="Flat", code="FLAT", amount="5", discount_type="fixed", currency="EUR"
        )
    )

    assert gql.calls[0].variables["input"]["fixedAmount"] == {"amount": "5", "currency": "EUR"}


async def test_create_raises_the_invalid_data_error_message_from_peek(gql):
    gql.queue({"createPromoCode": {"message": "code already exists"}})

    with pytest.raises(ValueError, match="code already exists"):
        await PromoCodeService(gql).create(VALID_INPUT)


async def test_create_raises_when_the_mutation_returns_no_data(gql):
    gql.queue_body({})
    with pytest.raises(ValueError, match="no data"):
        await PromoCodeService(gql).create(VALID_INPUT)


@pytest.mark.parametrize(
    ("input", "pattern"),
    [
        (replace(VALID_INPUT, name=""), "name is required"),
        (replace(VALID_INPUT, code=""), "code is required"),
        (replace(VALID_INPUT, amount=""), "amount is required"),
        (replace(VALID_INPUT, discount_type=""), "discountType is required"),
        (replace(VALID_INPUT, discount_type="bogus"), "must be either 'percent' or 'fixed'"),
        (replace(VALID_INPUT, amount="abc"), "amount must be a valid number"),
        (replace(VALID_INPUT, amount="nan"), "amount must be a valid number"),
        (replace(VALID_INPUT, discount_type="fixed", currency="usd"), "3 uppercase letters"),
    ],
)
async def test_create_rejects_invalid_input(gql, input, pattern):
    with pytest.raises(ValueError, match=pattern):
        await PromoCodeService(gql).create(input)
    assert gql.calls == []
