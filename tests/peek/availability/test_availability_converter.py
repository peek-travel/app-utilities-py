from peek_app_utilities.internal.peek.availability.availability_converter import (
    to_availability_time,
)
from peek_app_utilities.models.peek.availability_time import (
    Availability,
    AvailabilityTime,
    Duration,
    DurationLength,
)
from peek_app_utilities.models.peek.money import Money

NODE = {
    "id": "slot-1",
    "time": "10:00",
    "from": "2026-01-02T10:00:00Z",
    "end": "2026-01-02T11:00:00Z",
    "duration": {"name": "1h", "length": {"amount": 60, "unit": "MINUTES"}},
    "status": "AVAILABLE",
    "price": {"amount": "50.00", "currency": "USD", "formatted": "$50.00"},
    "availability": [{"qty": 10, "taken": 2, "resourceOptionId": "r1"}],
}


def test_maps_every_field_one_to_one():
    assert to_availability_time(NODE) == AvailabilityTime(
        id="slot-1",
        time="10:00",
        from_="2026-01-02T10:00:00Z",
        end="2026-01-02T11:00:00Z",
        duration=Duration(name="1h", length=DurationLength(amount=60, unit="MINUTES")),
        status="AVAILABLE",
        price=Money(amount="50.00", currency="USD", formatted="$50.00"),
        availability=[Availability(qty=10, taken=2, resource_option_id="r1")],
    )


def test_maps_a_missing_price_to_none_and_missing_availability_to_an_empty_list():
    result = to_availability_time({**NODE, "price": None, "availability": None})
    assert result.price is None
    assert result.availability == []


def test_degrades_a_sparse_price_node_to_empty_strings():
    result = to_availability_time({**NODE, "price": {"amount": None}})
    assert result.price == Money(amount="", currency="", formatted="")
