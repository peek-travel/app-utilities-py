from peek_app_utilities.internal.peek.resellers.channel_converter import from_channels_response
from peek_app_utilities.models.peek.channel import Agent, Channel


def test_maps_channels_and_flattens_nested_agents():
    response = {
        "channels": [
            {
                "id": "ch-1",
                "name": "Acme Tours",
                "notes": "preferred",
                "pricingModel": "NET",
                "state": "ACTIVE",
                "type": "RESELLER",
                "agents": {
                    "edges": [
                        {
                            "node": {
                                "email": "a@acme.com",
                                "name": "Agent A",
                                "internalNotes": "vip",
                                "phone": "+1",
                            }
                        }
                    ]
                },
            }
        ]
    }

    assert from_channels_response(response) == [
        Channel(
            id="ch-1",
            name="Acme Tours",
            notes="preferred",
            pricing_model="NET",
            state="ACTIVE",
            type="RESELLER",
            agents=[Agent(email="a@acme.com", name="Agent A", internal_notes="vip", phone="+1")],
        )
    ]


def test_treats_a_channel_with_no_agents_connection_as_having_no_agents():
    response = {
        "channels": [
            {
                "id": "ch-2",
                "name": "No Agents",
                "notes": None,
                "pricingModel": "GROSS",
                "state": "ACTIVE",
                "type": "RESELLER",
                "agents": None,
            }
        ]
    }

    assert from_channels_response(response)[0].agents == []


def test_returns_an_empty_list_for_none_data():
    assert from_channels_response(None) == []
    assert from_channels_response({}) == []


def test_degrades_a_sparse_channel_and_agent_instead_of_raising():
    [channel] = from_channels_response({"channels": [{"agents": {"edges": [{}]}}]})
    assert channel == Channel(
        id="",
        name="",
        notes=None,
        pricing_model="",
        state="",
        type="",
        agents=[Agent(email=None, name="", internal_notes=None, phone=None)],
    )
