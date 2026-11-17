from peek_app_utilities.internal.peek.resellers.reseller_service import ResellerService

CHANNEL: dict[str, object] = {
    "id": "ch-1",
    "name": "Acme",
    "notes": None,
    "pricingModel": "NET",
    "state": "ACTIVE",
    "type": "RESELLER",
    "agents": {"edges": []},
}


async def test_defaults_to_10_agents_per_channel_and_converts_the_response(gql):
    gql.queue({"channels": [CHANNEL]})

    channels = await ResellerService(gql).get_all_channels()

    assert [c.id for c in channels] == ["ch-1"]
    assert channels[0].agents == []
    assert gql.calls[0].variables["first"] == 10
    assert gql.calls[0].endpoint_name == "sales"
    assert "agents(first: $first)" in gql.calls[0].query


async def test_passes_through_a_custom_agents_per_channel_limit(gql):
    gql.queue({"channels": []})

    channels = await ResellerService(gql).get_all_channels(3)

    assert channels == []
    assert gql.calls[0].variables["first"] == 3


async def test_returns_an_empty_list_when_a_200_response_carries_no_data(gql):
    gql.queue_body({})
    assert await ResellerService(gql).get_all_channels() == []
