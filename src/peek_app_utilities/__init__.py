"""peek-app-utilities — the Python port of ``@peektravel/app-utilities``.

Public entry point. Exposes the access services, the clean data models, the
logger protocol, the webhook parsers, and the typed errors. The underlying
GraphQL queries, response shapes, and transport are intentionally internal.
"""

from peek_app_utilities.access_options import AccessOptions
from peek_app_utilities.access_service_config import BaseAccessServiceConfig
from peek_app_utilities.access_service_factory import (
    InstallAccessConfig,
    InstallAccessService,
    InstallAccessTarget,
    create_access_service_for_install,
)
from peek_app_utilities.acme_access_service import AcmeAccessService, AcmeAccessServiceConfig
from peek_app_utilities.cng_access_service import CngAccessService, CngAccessServiceConfig
from peek_app_utilities.errors import (
    AcmeApiError,
    AdminAccountRequiredError,
    AppUtilitiesError,
    CngApiError,
    CngPermissionError,
    PeekGraphQLError,
    PeekHttpError,
    PiiAccessDisabledError,
    RateLimitError,
)
from peek_app_utilities.internal.acme.products.product_service import AcmeProductService
from peek_app_utilities.internal.cng.products.product_service import CngProductService
from peek_app_utilities.internal.peek.account_users.account_user_service import (
    AccountUserService,
    AccountUserServiceOptions,
)
from peek_app_utilities.internal.peek.availability.availability_service import (
    AvailabilityService,
)
from peek_app_utilities.internal.peek.bookings.booking_service import (
    AddAddonInput,
    BookingService,
    BookingServiceOptions,
    CancelBookingResult,
)
from peek_app_utilities.internal.peek.bookings.booking_webhook import parse_booking_webhook
from peek_app_utilities.internal.peek.daily_notes.daily_note_service import DailyNoteService
from peek_app_utilities.internal.peek.installs.install_webhook import parse_install_webhook
from peek_app_utilities.internal.peek.memberships.membership_service import MembershipService
from peek_app_utilities.internal.peek.pricing.pricing_service import PricingService
from peek_app_utilities.internal.peek.products.product_service import (
    ProductService,
    ProductServiceOptions,
)
from peek_app_utilities.internal.peek.promo_codes.promo_code_service import (
    PromoCodeService,
    PromoCodeServiceOptions,
)
from peek_app_utilities.internal.peek.resellers.reseller_service import ResellerService
from peek_app_utilities.internal.peek.resource_pools.resource_pool_service import (
    ResourcePoolService,
)
from peek_app_utilities.internal.peek.reviews.review_service import ReviewService
from peek_app_utilities.internal.peek.timeslots.timeslot_service import TimeslotService
from peek_app_utilities.internal.peek.waivers.waiver_webhook import parse_waiver_webhook
from peek_app_utilities.logger import Logger, logging_adapter, noop_logger
from peek_app_utilities.models.acme.product import AcmeActivity, AcmeActivityTicket
from peek_app_utilities.models.cng.product import Activity, ActivityTicket
from peek_app_utilities.models.peek.account_user import AccountUser, AssignedActivity
from peek_app_utilities.models.peek.auth_token import (
    PEEK_PLATFORMS,
    PeekAuthTokenClaims,
    PeekAuthTokenUser,
    PeekPlatform,
)
from peek_app_utilities.models.peek.availability_time import (
    Availability,
    AvailabilityTime,
    AvailabilityTimesQuery,
    Duration,
    ResourceOptionQuantity,
)
from peek_app_utilities.models.peek.booking import (
    Booking,
    BookingReadOptions,
    BookingSearchBy,
    BookingTimeRangeSearch,
    CreateBookingGuest,
    CreateBookingInput,
    CreateBookingTicket,
    CreatedBooking,
    CustomQuestionAnswer,
    CustomQuestionAnswerInput,
    Guest,
    GuestMetadata,
    NoteMode,
    Price,
    Resource,
    ResourcePoolAssignment,
    Ticket,
)
from peek_app_utilities.models.peek.booking_addon import (
    BookingAddon,
    BookingAddonMoney,
    BookingAddonOption,
    BookingAddons,
    BookingAddonsMutationResult,
)
from peek_app_utilities.models.peek.booking_metadata import (
    MetaData,
    MetaDataBarcodeType,
    MetaDataDurationUnit,
    MetaDataValue,
    MetaDataVolumeUnit,
    MetaDataWeightUnit,
    SetMetaDataAttachmentInput,
    SetMetaDataGuestInput,
    SetMetaDataResult,
)
from peek_app_utilities.models.peek.booking_payment import (
    BookingPaymentsOnFile,
    InvoiceLinkResult,
    MakePaymentInput,
    MakePaymentResult,
    Payment,
    PaymentSource,
    RefundInput,
    RefundResult,
)
from peek_app_utilities.models.peek.channel import Agent, Channel
from peek_app_utilities.models.peek.custom_question import CustomQuestion, CustomQuestionOption
from peek_app_utilities.models.peek.daily_note import DailyNote
from peek_app_utilities.models.peek.install import INSTALL_STATUSES, InstallStatus, InstallWebhook
from peek_app_utilities.models.peek.membership import (
    Membership,
    MembershipPurchaseInput,
    PurchasedMembership,
)
from peek_app_utilities.models.peek.pricing import (
    ActivityOverrides,
    ClearOverridesInput,
    CreatedPricingEngine,
    CreateEngineInput,
    PricingActivityContext,
    PricingEngine,
    PricingMoney,
    PricingNamedRef,
    PricingOverride,
    PricingOverrideFilter,
    ResolvedOverride,
    ResolvedPricingOverride,
    ResolvedResourceOption,
    ResourceOptionOverride,
    UpdateEngineInput,
    UpsertOverridesInput,
    UpsertOverridesResult,
)
from peek_app_utilities.models.peek.product import (
    ACTIVITY_PRODUCT_TYPE,
    ADD_ON_PRODUCT_TYPE,
    RENTAL_PRODUCT_TYPE,
    Product,
    ProductMeetingLocation,
    ProductTicket,
)
from peek_app_utilities.models.peek.promo_code import (
    CreatedPromoCode,
    CreatePromoCodeInput,
    PromoCode,
    PromoCodeFixedAmount,
)
from peek_app_utilities.models.peek.resource_pool import (
    ResourcePool,
    ResourcePoolAccountUser,
    ResourcePoolMode,
)
from peek_app_utilities.models.peek.review import Guide, ProductReviewSummary, Review
from peek_app_utilities.models.peek.timeslot import (
    AssignedResource,
    AssignGuideResult,
    GuideAssignment,
    Timeslot,
    TimeslotFilter,
    UpdateTimeslotResult,
)
from peek_app_utilities.models.peek.waiver import Waiver
from peek_app_utilities.peek_access_service import PeekAccessService, PeekAccessServiceConfig

__all__ = [
    "ACTIVITY_PRODUCT_TYPE",
    "ADD_ON_PRODUCT_TYPE",
    "INSTALL_STATUSES",
    "PEEK_PLATFORMS",
    "RENTAL_PRODUCT_TYPE",
    "AccessOptions",
    "AccountUser",
    "AccountUserService",
    "AccountUserServiceOptions",
    "AcmeAccessService",
    "AcmeAccessServiceConfig",
    "AcmeActivity",
    "AcmeActivityTicket",
    "AcmeApiError",
    "AcmeProductService",
    "Activity",
    "ActivityOverrides",
    "ActivityTicket",
    "AddAddonInput",
    "AdminAccountRequiredError",
    "Agent",
    "AppUtilitiesError",
    "AssignGuideResult",
    "AssignedActivity",
    "AssignedResource",
    "Availability",
    "AvailabilityService",
    "AvailabilityTime",
    "AvailabilityTimesQuery",
    "BaseAccessServiceConfig",
    "Booking",
    "BookingAddon",
    "BookingAddonMoney",
    "BookingAddonOption",
    "BookingAddons",
    "BookingAddonsMutationResult",
    "BookingPaymentsOnFile",
    "BookingReadOptions",
    "BookingSearchBy",
    "BookingService",
    "BookingServiceOptions",
    "BookingTimeRangeSearch",
    "CancelBookingResult",
    "Channel",
    "ClearOverridesInput",
    "CngAccessService",
    "CngAccessServiceConfig",
    "CngApiError",
    "CngPermissionError",
    "CngProductService",
    "CreateBookingGuest",
    "CreateBookingInput",
    "CreateBookingTicket",
    "CreateEngineInput",
    "CreatePromoCodeInput",
    "CreatedBooking",
    "CreatedPricingEngine",
    "CreatedPromoCode",
    "CustomQuestion",
    "CustomQuestionAnswer",
    "CustomQuestionAnswerInput",
    "CustomQuestionOption",
    "DailyNote",
    "DailyNoteService",
    "Duration",
    "Guest",
    "GuestMetadata",
    "Guide",
    "GuideAssignment",
    "InstallAccessConfig",
    "InstallAccessService",
    "InstallAccessTarget",
    "InstallStatus",
    "InstallWebhook",
    "InvoiceLinkResult",
    "Logger",
    "MakePaymentInput",
    "MakePaymentResult",
    "Membership",
    "MembershipPurchaseInput",
    "MembershipService",
    "MetaData",
    "MetaDataBarcodeType",
    "MetaDataDurationUnit",
    "MetaDataValue",
    "MetaDataVolumeUnit",
    "MetaDataWeightUnit",
    "NoteMode",
    "Payment",
    "PaymentSource",
    "PeekAccessService",
    "PeekAccessServiceConfig",
    "PeekAuthTokenClaims",
    "PeekAuthTokenUser",
    "PeekGraphQLError",
    "PeekHttpError",
    "PeekPlatform",
    "PiiAccessDisabledError",
    "Price",
    "PricingActivityContext",
    "PricingEngine",
    "PricingMoney",
    "PricingNamedRef",
    "PricingOverride",
    "PricingOverrideFilter",
    "PricingService",
    "Product",
    "ProductMeetingLocation",
    "ProductReviewSummary",
    "ProductService",
    "ProductServiceOptions",
    "ProductTicket",
    "PromoCode",
    "PromoCodeFixedAmount",
    "PromoCodeService",
    "PromoCodeServiceOptions",
    "PurchasedMembership",
    "RateLimitError",
    "RefundInput",
    "RefundResult",
    "ResellerService",
    "ResolvedOverride",
    "ResolvedPricingOverride",
    "ResolvedResourceOption",
    "Resource",
    "ResourceOptionOverride",
    "ResourceOptionQuantity",
    "ResourcePool",
    "ResourcePoolAccountUser",
    "ResourcePoolAssignment",
    "ResourcePoolMode",
    "ResourcePoolService",
    "Review",
    "ReviewService",
    "SetMetaDataAttachmentInput",
    "SetMetaDataGuestInput",
    "SetMetaDataResult",
    "Ticket",
    "Timeslot",
    "TimeslotFilter",
    "TimeslotService",
    "UpdateEngineInput",
    "UpdateTimeslotResult",
    "UpsertOverridesInput",
    "UpsertOverridesResult",
    "Waiver",
    "create_access_service_for_install",
    "logging_adapter",
    "noop_logger",
    "parse_booking_webhook",
    "parse_install_webhook",
    "parse_waiver_webhook",
]
