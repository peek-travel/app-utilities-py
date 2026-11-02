from peek_app_utilities.internal.peek.availability.availability_service import (
    AvailabilityService,
)
from peek_app_utilities.models.peek.availability_time import (
    Availability,
    AvailabilityTime,
    AvailabilityTimesQuery,
    Duration,
    DurationLength,
    ResourceOptionQuantity,
)

SLOT = {
    "id": "slot-1",
    "time": "10:00",
    "from": "2026-01-02T10:00:00Z",
    "end": "2026-01-02T11:00:00Z",
    "duration": {"name": "1h", "length": {"amount": 60, "unit": "MINUTES"}},
    "status": "AVAILABLE",
    "availability": [{"qty": 10, "taken": 2, "resourceOptionId": "r1"}],
}


async def test_sends_the_query_variables_and_returns_the_slots(gql):
    gql.queue({"availabilityTimes": [SLOT]})

    result = await AvailabilityService(gql).get_availability_times(
        AvailabilityTimesQuery(
            activity_id="act-1",
            date="2026-01-02",
            resource_option_quantities=[
                ResourceOptionQuantity(resource_option_id="r1", quantity=2)
            ],
        )
    )

    assert result == [
        AvailabilityTime(
            id="slot-1",
            time="10:00",
            from_="2026-01-02T10:00:00Z",
            end="2026-01-02T11:00:00Z",
            duration=Duration(name="1h", length=DurationLength(amount=60, unit="MINUTES")),
            status="AVAILABLE",
            availability=[Availability(qty=10, taken=2, resource_option_id="r1")],
        )
    ]
    call = gql.calls[0]
    assert call.endpoint_name == "sales"
    assert call.variables["activityId"] == "act-1"
    assert call.variables["date"] == "2026-01-02"
    assert call.variables["resourceOptionQuantities"] == [{"resourceOptionId": "r1", "quantity": 2}]
    assert "availabilityTimes(activityId: $activityId" in call.query


async def test_returns_an_empty_list_when_a_200_response_carries_no_data(gql):
    gql.queue_body({})
    result = await AvailabilityService(gql).get_availability_times(
        AvailabilityTimesQuery(
            activity_id="act-1", date="2026-01-02", resource_option_quantities=[]
        )
    )
    assert result == []
    assert gql.calls[0].variables["resourceOptionQuantities"] == []


async def test_degrades_a_sparse_slot_instead_of_raising(gql):
    gql.queue({"availabilityTimes": [{"id": "slot-2"}]})

    [slot] = await AvailabilityService(gql).get_availability_times(
        AvailabilityTimesQuery(
            activity_id="act-1", date="2026-01-02", resource_option_quantities=[]
        )
    )

    assert slot == AvailabilityTime(
        id="slot-2",
        time="",
        from_="",
        end="",
        duration=Duration(name="", length=DurationLength(amount=0, unit="")),
        status="",
        availability=[],
    )
