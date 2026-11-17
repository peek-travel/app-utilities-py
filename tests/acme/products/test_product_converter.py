from peek_app_utilities.internal.acme.products.product_converter import from_template_nodes
from peek_app_utilities.models.acme.product import AcmeActivity


def test_maps_a_published_node_to_an_activity_using_the_background_color():
    nodes = [
        {
            "id": "61f99bfe62bd1f467c39771f",
            "name": "General Admission",
            "type": "standard",
            "admissionType": "standard",
            "reviewState": "published",
            "colorCategory": {"backgroundColor": "#00695c", "textColor": "#ffffff"},
        }
    ]
    assert from_template_nodes(nodes) == [  # type: ignore[arg-type]
        AcmeActivity(
            product_id="61f99bfe62bd1f467c39771f",
            name="General Admission",
            type="standard",
            color="#00695c",
            tickets=[],
        )
    ]


def test_filters_out_non_published_templates():
    nodes = [
        {"id": "a", "name": "Draft", "reviewState": "draft"},
        {"id": "b", "name": "Archived", "reviewState": "archived"},
        {"id": "c", "name": "Live", "reviewState": "published"},
        "junk",
    ]
    assert from_template_nodes(nodes) == [  # type: ignore[arg-type]
        AcmeActivity(product_id="c", name="Live", type="standard", color="#d1d1d1", tickets=[])
    ]


def test_applies_defaults_for_missing_or_null_optional_fields():
    nodes = [{"id": "d", "name": "Bare", "reviewState": "published", "colorCategory": None}]
    assert from_template_nodes(nodes) == [  # type: ignore[arg-type]
        AcmeActivity(product_id="d", name="Bare", type="standard", color="#d1d1d1", tickets=[])
    ]


def test_coerces_missing_id_name_and_null_color_to_defaults():
    nodes = [
        {"reviewState": "published", "type": "vip", "colorCategory": {"backgroundColor": None}}
    ]
    assert from_template_nodes(nodes) == [  # type: ignore[arg-type]
        AcmeActivity(product_id="", name="", type="vip", color="#d1d1d1", tickets=[])
    ]


def test_returns_an_empty_list_for_no_nodes():
    assert from_template_nodes([]) == []
