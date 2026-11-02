"""Authenticated root entry point to the Peek backoffice API.

Configure one instance per install with everything needed to authenticate and
reach the API. The access service owns the shared, authenticated transport (it
mints and caches tokens on demand) and hands out per-resource service objects —
e.g. :meth:`PeekAccessService.get_product_service` — that carry the
resource-specific business logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import TracebackType
from typing import Any, Final, Self

from peek_app_utilities.access_options import (
    ResolvedAccessOptions,
    resolve_access_options,
)
from peek_app_utilities.access_service_config import (
    BaseAccessServiceConfig,
    GatewayMode,
    create_token_manager,
    require_non_empty,
    resolve_base_api_url,
    resolve_retry_delays,
)
from peek_app_utilities.internal.peek.account_users.account_user_service import (
    AccountUserService,
)
from peek_app_utilities.internal.peek.availability.availability_service import (
    AvailabilityService,
)
from peek_app_utilities.internal.peek.bookings.booking_service import (
    BookingService,
    BookingServiceOptions,
)
from peek_app_utilities.internal.peek.daily_notes.daily_note_service import DailyNoteService
from peek_app_utilities.internal.peek.gateway_endpoints import (
    V2_EXTENDABLE_SLUG,
    peek_api_endpoints,
)
from peek_app_utilities.internal.peek.graphql_client import GraphQLClient, GraphQLClientOptions
from peek_app_utilities.internal.peek.memberships.membership_service import MembershipService
from peek_app_utilities.internal.peek.peek_auth_token import (
    map_peek_token_user,
    verify_peek_jwt,
)
from peek_app_utilities.internal.peek.pricing.pricing_service import PricingService
from peek_app_utilities.internal.peek.products.product_service import (
    ProductService,
    ProductServiceOptions,
)
from peek_app_utilities.internal.peek.promo_codes.promo_code_service import PromoCodeService
from peek_app_utilities.internal.peek.resellers.reseller_service import ResellerService
from peek_app_utilities.internal.peek.resource_pools.resource_pool_service import (
    ResourcePoolService,
)
from peek_app_utilities.internal.peek.reviews.review_service import ReviewService
from peek_app_utilities.internal.peek.timeslots.timeslot_service import TimeslotService
from peek_app_utilities.internal.rest_access import OwnedHttpClient
from peek_app_utilities.logger import noop_logger
from peek_app_utilities.models.peek.auth_token import PeekAuthTokenClaims

SERVICE_NAME: Final = "PeekAccessService"
DEFAULT_BASE_URL: Final = "https://apps.peekapis.com/backoffice-gql"
"""Default backoffice GraphQL base URL (legacy v1)."""
DEFAULT_V2_BASE_URL: Final = "https://app-registry.peeklabs.com/installations-api"
"""Default base URL when operating in v2 mode."""
_V2_MODE: Final = "v2"


@dataclass(frozen=True, slots=True, kw_only=True)
class PeekAccessServiceConfig(BaseAccessServiceConfig):
    """Configuration for a :class:`PeekAccessService`. Extends the shared
    :class:`BaseAccessServiceConfig` with the Peek-specific extras below."""

    gateway_key: str | None = None
    """API gateway key, sent as the ``pk-api-key`` header. Required in the legacy
    v1 mode; not used with ``api_url`` or ``mode="v2"``."""
    mode: GatewayMode | None = None
    """Gateway mode. ``"v2"`` routes through the app-registry installations API
    (``base_url/app_id/peek_backoffice_api-v1``). Default (``None``) is the
    legacy v1 backoffice GraphQL gateway. ``api_url``, when set, supersedes this."""
    item_options_page_size: int | None = None
    """Page size for cursor-paginated item options. Default: 50."""


class PeekAccessService:
    """Authenticated root entry point to the Peek backoffice API.

    Construct one instance per install, then call the ``get_<resource>_service()``
    accessors to reach the resource-specific operations. Each accessor returns a
    memoized service bound to the shared, authenticated transport — the access
    service mints and caches a short-lived JWT on demand.

    Example::

        async with PeekAccessService(PeekAccessServiceConfig(
            install_id="install-123",
            jwt_secret=os.environ["PEEK_INTERNAL_SECRET"],
            issuer=os.environ["APP_NAME"],
            api_url=install.api_url,
        )) as peek:
            products = await peek.get_product_service().get_all_products()
            booking = await peek.get_booking_service().get_by_id("b_abc123")

    :raises ValueError: from the constructor when any required config field is
        empty (``install_id``, ``jwt_secret``, ``issuer`` always; ``app_id`` and
        ``gateway_key`` only in the legacy ``base_url`` mode), or when
        ``api_url`` carries another platform's slug.
    """

    def __init__(self, config: PeekAccessServiceConfig) -> None:
        has_api_url = bool(config.api_url)
        is_v2 = config.mode == _V2_MODE
        require_non_empty(config.install_id, "install_id", SERVICE_NAME)
        require_non_empty(config.jwt_secret, "jwt_secret", SERVICE_NAME)
        require_non_empty(config.issuer, "issuer", SERVICE_NAME)
        # `app_id` is only a URL path segment for the legacy `base_url` mode.
        if not has_api_url:
            require_non_empty(config.app_id, "app_id", SERVICE_NAME)
        # The registry app endpoint authenticates on the JWT alone (like v2), so
        # the `pk-api-key` gateway key is only required in the legacy v1 mode.
        if not has_api_url and not is_v2:
            require_non_empty(config.gateway_key, "gateway_key", SERVICE_NAME)

        self._jwt_secret = config.jwt_secret
        self._issuer = config.issuer
        self._http = OwnedHttpClient(config.http_client)
        tokens = create_token_manager(config)

        # Registry modes (an app-endpoint `api_url`, or legacy v2) route `sales`
        # through the `peek_backoffice_api-v1` slug; the legacy v1 gateway has
        # no slug.
        use_registry_slug = has_api_url or is_v2
        default_base_url = DEFAULT_V2_BASE_URL if is_v2 else DEFAULT_BASE_URL
        if config.api_url:
            base_api_url = resolve_base_api_url(config.api_url, V2_EXTENDABLE_SLUG, SERVICE_NAME)
        else:
            base_api_url = f"{config.base_url or default_base_url}/{config.app_id}"
        self._client = GraphQLClient(
            GraphQLClientOptions(
                base_api_url=base_api_url,
                endpoints=peek_api_endpoints(use_registry_slug),
                gateway_key=config.gateway_key,
                get_token=tokens.get_token,
                retry_delays_ms=resolve_retry_delays(config),
                logger=config.logger or noop_logger,
                http_client=self._http.client,
            )
        )

        self._product_service_options = ProductServiceOptions(
            item_options_page_size=config.item_options_page_size
        )
        self._access_options: ResolvedAccessOptions = resolve_access_options(config.access_options)

        self._product_service: ProductService | None = None
        self._account_user_service: AccountUserService | None = None
        self._resource_pool_service: ResourcePoolService | None = None
        self._timeslot_service: TimeslotService | None = None
        self._reseller_service: ResellerService | None = None
        self._promo_code_service: PromoCodeService | None = None
        self._pricing_service: PricingService | None = None
        self._daily_note_service: DailyNoteService | None = None
        self._availability_service: AvailabilityService | None = None
        self._membership_service: MembershipService | None = None
        self._booking_services: dict[str, BookingService] = {}
        self._review_service: ReviewService | None = None

    # ─── Access-level concerns ─────────────────────────────────────────────

    def verify_peek_auth_token(self, token: str) -> PeekAuthTokenClaims:
        """Verifies a Peek auth token issued by the app registry and returns the
        decoded claims.

        Validates the HMAC signature (using this service's ``jwt_secret``), the
        token expiry, the ``"app_registry_v2"`` issuer, and the ``"Joken"``
        audience. Pass the raw ``x-peek-auth`` request header value — a leading
        ``Bearer `` prefix is stripped for you.

        Claim *extraction* is defensive: once the signature verifies, a token with
        no ``user`` block yields ``claims.user is None``, and any individual user
        field that is absent or a sentinel (``""``, ``"null"``) is normalized to
        ``None``. This method never raises on a shape problem — only on a
        verification failure.

        :raises jwt.ExpiredSignatureError: token has expired
        :raises jwt.ImmatureSignatureError: token not yet valid
        :raises jwt.InvalidTokenError: signature invalid, wrong issuer/audience,
            or token malformed (base class of the above)
        """
        payload: dict[str, Any] = verify_peek_jwt(token, self._jwt_secret)
        return PeekAuthTokenClaims(
            install_id=str(payload.get("sub") or ""),
            display_version=str(payload.get("display_version") or ""),
            user=map_peek_token_user(payload.get("user")),
        )

    async def aclose(self) -> None:
        """Closes the package-owned HTTP client (a caller-supplied one is left open)."""
        await self._http.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    # ─── Resource-service accessors (lazily created, memoized) ─────────────

    def get_product_service(self) -> ProductService:
        """The :class:`ProductService` for this install, bound to the shared
        authenticated transport. Created lazily and reused."""
        if self._product_service is None:
            self._product_service = ProductService(self._client, self._product_service_options)
        return self._product_service

    def get_account_user_service(self) -> AccountUserService:
        """The :class:`AccountUserService` for this install. Created lazily and reused."""
        if self._account_user_service is None:
            self._account_user_service = AccountUserService(self._client)
        return self._account_user_service

    def get_resource_pool_service(self) -> ResourcePoolService:
        """The :class:`ResourcePoolService` for this install. Created lazily and reused."""
        if self._resource_pool_service is None:
            self._resource_pool_service = ResourcePoolService(self._client)
        return self._resource_pool_service

    def get_timeslot_service(self) -> TimeslotService:
        """The :class:`TimeslotService` for this install. Created lazily and reused;
        its guide assignment composes the resource-pool and account-user services."""
        if self._timeslot_service is None:
            self._timeslot_service = TimeslotService(
                self._client,
                resource_pool_service=self.get_resource_pool_service(),
                account_user_service=self.get_account_user_service(),
            )
        return self._timeslot_service

    def get_reseller_service(self) -> ResellerService:
        """The :class:`ResellerService` for this install. Created lazily and reused."""
        if self._reseller_service is None:
            self._reseller_service = ResellerService(self._client)
        return self._reseller_service

    def get_promo_code_service(self) -> PromoCodeService:
        """The :class:`PromoCodeService` for this install. Created lazily and reused."""
        if self._promo_code_service is None:
            self._promo_code_service = PromoCodeService(self._client)
        return self._promo_code_service

    def get_pricing_service(self) -> PricingService:
        """The :class:`PricingService` for this install. Created lazily and reused."""
        if self._pricing_service is None:
            self._pricing_service = PricingService(self._client)
        return self._pricing_service

    def get_daily_note_service(self) -> DailyNoteService:
        """The :class:`DailyNoteService` for this install. Created lazily and reused."""
        if self._daily_note_service is None:
            self._daily_note_service = DailyNoteService(self._client)
        return self._daily_note_service

    def get_availability_service(self) -> AvailabilityService:
        """The :class:`AvailabilityService` for this install. Created lazily and reused."""
        if self._availability_service is None:
            self._availability_service = AvailabilityService(self._client)
        return self._availability_service

    def get_membership_service(self) -> MembershipService:
        """The :class:`MembershipService` for this install. Created lazily and reused."""
        if self._membership_service is None:
            self._membership_service = MembershipService(self._client)
        return self._membership_service

    def get_booking_service(self, integrator: str | None = None) -> BookingService:
        """The :class:`BookingService` for this install. Instances are created
        lazily and reused per ``integrator``.

        ``integrator`` scopes ``get_meta_data`` results to a custom integrator id.
        **Do not set it** unless Peek engineering created a custom integrator id
        for this integration — omit it and the correct default is used.
        """
        resolved = integrator if integrator is not None else self._issuer
        service = self._booking_services.get(resolved)
        if service is None:
            service = BookingService(
                self._client,
                product_service=self.get_product_service(),
                options=BookingServiceOptions(
                    access_options=self._access_options, integrator=resolved
                ),
            )
            self._booking_services[resolved] = service
        return service

    def get_review_service(self) -> ReviewService:
        """The :class:`ReviewService` for this install. Created lazily and reused."""
        if self._review_service is None:
            self._review_service = ReviewService(self._client, self._access_options)
        return self._review_service
