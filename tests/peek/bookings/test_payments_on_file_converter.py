from peek_app_utilities.internal.peek.bookings.payments_on_file_converter import (
    from_payments_on_file_response,
)
from peek_app_utilities.models.peek.booking_payment import (
    BookingPaymentsOnFile,
    Payment,
    PaymentAmount,
    PaymentSource,
)


def usd(amount: str) -> dict[str, str]:
    return {"amount": amount, "currency": "USD"}


class TestFromPaymentsOnFileResponse:
    def test_aggregates_payments_under_their_source(self):
        response = {
            "sales": {
                "edges": [
                    {
                        "node": {
                            "order": {
                                "id": "o_1",
                                "paymentSources": [
                                    {"description": "Visa", "id": "ps-1", "type": "CARD"},
                                    {"description": "Cash", "id": "ps-2", "type": "CASH"},
                                ],
                                "payments": [
                                    {
                                        "id": "pay-1",
                                        "paymentSource": {"id": "ps-1"},
                                        "appliedAt": "2026-01-02T10:00:00Z",
                                        "currentAmount": usd("50"),
                                        "refundableAmount": usd("50"),
                                    },
                                    {
                                        "id": "pay-2",
                                        "paymentSource": {"id": "ps-1"},
                                        "appliedAt": "2026-01-03T10:00:00Z",
                                        "currentAmount": usd("25"),
                                        "refundableAmount": usd("25"),
                                    },
                                    {
                                        "id": "pay-orphan",
                                        "paymentSource": None,
                                        "appliedAt": "2026-01-04T10:00:00Z",
                                        "currentAmount": usd("1"),
                                        "refundableAmount": usd("1"),
                                    },
                                ],
                            }
                        }
                    }
                ]
            }
        }

        result = from_payments_on_file_response(response, "b_1")
        assert result == BookingPaymentsOnFile(
            booking_id="b_1",
            order_id="o_1",
            payments_on_file=[
                PaymentSource(
                    description="Visa",
                    id="ps-1",
                    type="CARD",
                    payments=[
                        Payment(
                            id="pay-1",
                            paid_at="2026-01-02",
                            current_amount=PaymentAmount(amount="50", currency="USD"),
                            refundable_amount=PaymentAmount(amount="50", currency="USD"),
                        ),
                        Payment(
                            id="pay-2",
                            paid_at="2026-01-03",
                            current_amount=PaymentAmount(amount="25", currency="USD"),
                            refundable_amount=PaymentAmount(amount="25", currency="USD"),
                        ),
                    ],
                ),
                PaymentSource(description="Cash", id="ps-2", type="CASH", payments=None),
            ],
        )

    def test_returns_none_when_the_booking_is_not_found(self):
        assert from_payments_on_file_response({"sales": {"edges": []}}, "b_1") is None
        assert from_payments_on_file_response(None, "b_1") is None

    def test_defaults_an_absent_order_to_an_empty_result(self):
        result = from_payments_on_file_response({"sales": {"edges": [{"node": {}}]}}, "b_1")
        assert result == BookingPaymentsOnFile(booking_id="b_1", order_id="", payments_on_file=[])
