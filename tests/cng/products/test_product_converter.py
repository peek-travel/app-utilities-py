from peek_app_utilities.internal.cng.products.product_converter import from_product_nodes
from peek_app_utilities.models.cng.product import Activity


def test_maps_a_fully_populated_node_to_an_activity():
    nodes = [
        {
            "id": 1000171,
            "name": "10 students + Complimentary chaperone",
            "slug": "10-students-complimentary-chaperone",
            "status": "ACTIVE",
            "access_control_color_hex": "#1A2B3C",
            "custom_access_control_color": True,
        }
    ]
    assert from_product_nodes(nodes) == [  # type: ignore[arg-type]
        Activity(
            product_id="1000171",
            name="10 students + Complimentary chaperone",
            type="ACTIVITY",
            color="#1A2B3C",
            tickets=[],
        )
    ]


def test_applies_defaults_for_missing_or_null_optional_fields():
    nodes = [
        {
            "id": 1000171,
            "name": "Bare",
            "access_control_color_hex": None,
            "custom_access_control_color": False,
        }
    ]
    assert from_product_nodes(nodes) == [  # type: ignore[arg-type]
        Activity(product_id="1000171", name="Bare", type="ACTIVITY", color="", tickets=[])
    ]


def test_accepts_a_string_id_and_coerces_a_missing_name():
    assert from_product_nodes([{"id": "1000171"}]) == [
        Activity(product_id="1000171", name="", type="ACTIVITY", color="", tickets=[])
    ]


def test_coerces_a_missing_id_to_an_empty_string():
    assert from_product_nodes([{"name": "No id"}]) == [
        Activity(product_id="", name="No id", type="ACTIVITY", color="", tickets=[])
    ]


def test_returns_an_empty_list_for_no_nodes():
    assert from_product_nodes([]) == []
