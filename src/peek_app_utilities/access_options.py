"""Cross-cutting options that govern what data an access service will read and
expose.

Passed once when constructing an access service and threaded down to the
resource services (and the webhook parsers) so a single object controls
behaviour everywhere, rather than a boolean being passed hand-to-hand.

Kept deliberately small — today it carries a single PII toggle, but new
cross-cutting flags slot in here without changing any downstream signatures.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class AccessOptions:
    """Options controlling PII exposure across an access service's reads."""

    full_customer_access: bool | None = None
    """When ``True``, customer PII (guest names/emails/phones, custom question
    answers, the customer booking-portal URL, waiver participant details, …) is
    requested and returned, and payment/booking-modification operations are
    available.

    When ``False`` (the default), those PII fields are never requested and come
    back ``None``/empty, and the payment/booking-modification operations that
    touch customer financial data are disabled (they raise
    :class:`~peek_app_utilities.errors.PiiAccessDisabledError`).
    """


@dataclass(frozen=True, slots=True, kw_only=True)
class ResolvedAccessOptions:
    """A fully-resolved :class:`AccessOptions` with every flag defaulted."""

    full_customer_access: bool


def resolve_access_options(options: AccessOptions | None = None) -> ResolvedAccessOptions:
    """Resolves a possibly-absent :class:`AccessOptions` into a concrete object
    with every flag defaulted. ``full_customer_access`` defaults to ``False``."""
    enabled = options.full_customer_access if options is not None else None
    return ResolvedAccessOptions(full_customer_access=bool(enabled))
