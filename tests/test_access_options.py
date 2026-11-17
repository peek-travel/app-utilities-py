from peek_app_utilities.access_options import (
    AccessOptions,
    ResolvedAccessOptions,
    resolve_access_options,
)


def test_defaults_full_customer_access_to_false_when_no_options_are_given():
    expected = ResolvedAccessOptions(full_customer_access=False)
    assert resolve_access_options() == expected
    assert resolve_access_options(None) == expected
    assert resolve_access_options(AccessOptions()) == expected


def test_passes_through_an_explicit_full_customer_access_value():
    assert resolve_access_options(
        AccessOptions(full_customer_access=True)
    ) == ResolvedAccessOptions(full_customer_access=True)
    assert resolve_access_options(
        AccessOptions(full_customer_access=False)
    ) == ResolvedAccessOptions(full_customer_access=False)
