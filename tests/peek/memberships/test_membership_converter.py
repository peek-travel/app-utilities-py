from peek_app_utilities.internal.peek.memberships.membership_converter import (
    from_memberships_response,
)
from peek_app_utilities.models.peek.membership import Membership


def test_flattens_each_variant_into_its_own_record():
    response = {
        "memberships": [
            {
                "id": "m1",
                "name": "Gold",
                "membershipVariants": [
                    {
                        "id": "v1",
                        "description": "annual",
                        "imageUrl": "https://img/v1.png",
                        "externalName": "Gold Annual",
                        "internalName": "gold-annual",
                    },
                    {
                        "id": "v2",
                        "description": None,
                        "imageUrl": None,
                        "externalName": "Gold Monthly",
                        "internalName": "gold-monthly",
                    },
                ],
            }
        ]
    }

    assert from_memberships_response(response) == [
        Membership(
            id="m1",
            membership_variant_id="v1",
            description="annual",
            external_name="Gold Annual",
            image_url="https://img/v1.png",
            internal_name="gold-annual",
            display_name="Gold",
        ),
        Membership(
            id="m1",
            membership_variant_id="v2",
            description=None,
            external_name="Gold Monthly",
            image_url=None,
            internal_name="gold-monthly",
            display_name="Gold",
        ),
    ]


def test_produces_no_records_for_a_membership_with_no_variants():
    response = {"memberships": [{"id": "m2", "name": "Empty", "membershipVariants": []}]}
    assert from_memberships_response(response) == []


def test_tolerates_a_membership_with_no_membership_variants_field():
    response = {"memberships": [{"id": "m3", "name": "Bare"}]}
    assert from_memberships_response(response) == []


def test_returns_an_empty_list_for_none_data():
    assert from_memberships_response(None) == []


def test_degrades_missing_variant_fields_to_empty_strings():
    [membership] = from_memberships_response({"memberships": [{"membershipVariants": [{}]}]})
    assert membership == Membership(
        id="",
        membership_variant_id="",
        description=None,
        external_name="",
        image_url=None,
        internal_name="",
        display_name="",
    )
