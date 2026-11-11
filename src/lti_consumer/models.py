"""
LTI configuration and linking models.
"""
import json
import logging
import uuid
from typing import NamedTuple

from ccx_keys.locator import CCXBlockUsageLocator
from config_models.models import ConfigurationModel
from Cryptodome.PublicKey import RSA
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from edx_django_utils.monitoring import function_trace
from jsonfield import JSONField
from jwt import get_algorithm_by_name
from opaque_keys.edx.django.models import CourseKeyField, UsageKeyField
from opaque_keys.edx.keys import CourseKey

from lti_consumer.exceptions import ReusableConfigurationUnavailable
from lti_consumer.filters import get_external_config_from_filter

# LTI 1.1
from lti_consumer.lti_1p1.consumer import LtiConsumer1p1

# LTI 1.3
from lti_consumer.lti_1p3.consumer import LtiAdvantageConsumer, LtiProctoringConsumer
from lti_consumer.lti_1p3.exceptions import InvalidRsaKey
from lti_consumer.lti_1p3.key_handlers import PlatformKeyHandler
from lti_consumer.plugin import compat
from lti_consumer.utils import (
    EXTERNAL_ID_REGEX,
    choose_lti_1p3_redirect_uris,
    external_multiple_launch_urls_enabled,
    get_lti_ags_lineitems_url,
    get_lti_api_base,
    get_lti_deeplinking_response_url,
    get_lti_nrps_context_membership_url,
    model_to_dict,
)

log = logging.getLogger(__name__)


def generate_client_id():
    """
    Generates a random UUID string.
    """
    return str(uuid.uuid4())


class RuntimeIdentity(NamedTuple):
    """Stored LTI 1.3 registration material that a runtime request needs."""

    client_id: str
    deployment_id: str
    private_key: str
    private_key_id: str
    public_jwk: dict
    tool_public_key: str
    tool_keyset_url: str


def _validated_public_jwk(private_key, private_key_id, stored_jwk):
    """Parse a stored public keyset and check that it carries the signing key.

    A malformed keyset, an unparsable signing key or a key that does not belong to the
    stored private key denies the request instead of raising a parser error or
    publishing unusable material.
    """
    try:
        key_set = json.loads(stored_jwk)
    except (TypeError, ValueError) as exc:
        raise ReusableConfigurationUnavailable("The stored public keyset is not valid JSON.") from exc

    keys = key_set.get('keys') if isinstance(key_set, dict) else None
    if not isinstance(keys, list) or not all(isinstance(key, dict) for key in keys):
        raise ReusableConfigurationUnavailable("The stored public keyset is not a keyset.")

    try:
        key_handler = PlatformKeyHandler(key_pem=private_key, kid=private_key_id)
    except (InvalidRsaKey, TypeError) as exc:
        # PyJWT raises TypeError, not InvalidKeyError, for a password-encrypted PEM.
        raise ReusableConfigurationUnavailable("The stored signing key is not a valid RSA key.") from exc

    loaded_key = key_handler.key.key if key_handler.key else None
    if not hasattr(loaded_key, 'public_key'):
        raise ReusableConfigurationUnavailable("The stored signing key is not a private RSA key.")

    expected = json.loads(get_algorithm_by_name('RS256').to_jwk(loaded_key.public_key()))
    expected['kid'] = private_key_id
    matching = [
        key for key in keys
        if key.get('kid') == private_key_id and
        all(key.get(field) == expected.get(field) for field in ('kty', 'n', 'e'))
    ]
    if not matching:
        raise ReusableConfigurationUnavailable("The stored public keyset does not match the signing key.")

    return key_set


class Lti1p3Passport(models.Model):
    """
    Model to store LTI 1.3 keys.
    """
    name = models.CharField(max_length=255, null=True, blank=True)
    context_key = models.CharField(max_length=255, null=True, blank=True)
    passport_id = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)

    lti_1p3_internal_private_key = models.TextField(
        blank=True,
        help_text=_("Platform's generated Private key. Keep this value secret."),
    )

    lti_1p3_internal_private_key_id = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Platform's generated Private key ID"),
    )

    lti_1p3_internal_public_jwk = models.TextField(
        blank=True,
        help_text=_("Platform's generated JWK keyset."),
    )

    lti_1p3_client_id = models.CharField(
        max_length=255,
        default=generate_client_id,
        help_text=_("Client ID used by LTI tool"),
    )

    lti_1p3_tool_public_key = models.TextField(
        "LTI 1.3 Tool Public Key",
        blank=True,
        help_text='This is the LTI Tool\'s public key. This should be provided by the LTI Tool. '
                  'One of either lti_1p3_tool_public_key or lti_1p3_tool_keyset_url must not be blank.'
    )

    lti_1p3_tool_keyset_url = models.CharField(
        "LTI 1.3 Tool Keyset URL",
        max_length=500,
        blank=True,
        help_text='This is the LTI Tool\'s JWK (JSON Web Key) Keyset (JWKS) URL. This should be provided by the LTI '
                  'Tool. One of either lti_1p3_tool_public_key or lti_1p3_tool_keyset_url must not be blank.'
    )

    def _generate_lti_1p3_keys_if_missing(self):
        """
        Generate LTI 1.3 RSA256 keys if missing.

        If either the public or private key are missing, regenerate them.
        The LMS provides a keyset endpoint, so key rotations don't cause any issues
        for LTI launches (as long as they have a different kid).
        """
        # Generate new private key if not present
        if not self.lti_1p3_internal_private_key:
            # Private key
            private_key = RSA.generate(2048)
            self.lti_1p3_internal_private_key_id = str(uuid.uuid4())
            self.lti_1p3_internal_private_key = private_key.export_key('PEM').decode('utf-8')

            # Clear public key if any to allow regeneration
            # in the code below
            self.lti_1p3_internal_public_jwk = ''

        if not self.lti_1p3_internal_public_jwk:
            # Public key
            key_handler = PlatformKeyHandler(
                key_pem=self.lti_1p3_internal_private_key,
                kid=self.lti_1p3_internal_private_key_id,
            )
            self.lti_1p3_internal_public_jwk = json.dumps(
                key_handler.get_public_jwk()
            )

        # Doesn't do anything if model didn't change
        self.save()

    @property
    def lti_1p3_private_key(self):
        """
        Return the platform's private key used in LTI 1.3 authentication flows.
        """
        self._generate_lti_1p3_keys_if_missing()
        return self.lti_1p3_internal_private_key

    @property
    def lti_1p3_private_key_id(self):
        """
        Return the platform's private key ID used in LTI 1.3 authentication flows.
        """
        self._generate_lti_1p3_keys_if_missing()
        return self.lti_1p3_internal_private_key_id

    @property
    def lti_1p3_public_jwk(self):
        """
        Return the platform's public keys used in LTI 1.3 authentication flows.
        """
        self._generate_lti_1p3_keys_if_missing()
        return json.loads(self.lti_1p3_internal_public_jwk)

    def __str__(self):
        return f'Lti1p3Passport: {self.name} - {self.passport_id}'

    def clean(self):
        if self.lti_1p3_tool_public_key == "" and self.lti_1p3_tool_keyset_url == "":
            raise ValidationError({
                "config_store": _(
                    "LTI Configuration stored on the model for LTI 1.3 must have a value for one of "
                    "lti_1p3_tool_public_key or lti_1p3_tool_keyset_url."
                ),
            })

    class Meta:
        app_label = 'lti_consumer'


class ReusableLtiConfiguration(models.Model):
    """
    A reusable LTI configuration, catalog entry and LTI 1.3 passport.

    This is a new table beside the retained ``Lti1p3Passport``: one row is one
    registration, ``passport_id`` is the only stored identity, and every
    ``LtiConfiguration.reusable_configuration`` reference binds a placement to it.
    Placement data (launch context, Deep Linking content, line items, grades)
    stays on ``LtiConfiguration``.

    Credentials and signing material are stored exactly as they were on a
    passport: ordinary row reads and saves do not generate RSA material. Callers
    provision keys explicitly with ``generate_lti_1p3_keys_if_missing``; migrations
    must read the concrete stored fields.
    """

    LTI_1P1 = 'lti_1p1'
    LTI_1P3 = 'lti_1p3'
    LTI_VERSION_CHOICES = [
        (LTI_1P1, _('LTI 1.1')),
        (LTI_1P3, _('LTI 1.3')),
    ]

    # Passport identity, credentials and signing material.
    name = models.CharField(max_length=255, null=True, blank=True)
    context_key = models.CharField(_("Context key"), max_length=255, null=True, blank=True)
    passport_id = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)

    lti_1p3_internal_private_key = models.TextField(
        blank=True,
        help_text=_("Platform's generated Private key. Keep this value secret."),
    )

    lti_1p3_internal_private_key_id = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Platform's generated Private key ID"),
    )

    lti_1p3_internal_public_jwk = models.TextField(
        blank=True,
        help_text=_("Platform's generated JWK keyset."),
    )

    # shortcut: Client ID equality follows DB collation and carries no uniqueness guarantee;
    # add portable matching only if cross-backend consistency is required.
    lti_1p3_client_id = models.CharField(
        max_length=255,
        default=generate_client_id,
        null=True,
        blank=True,
        help_text=_("Client ID used by LTI tool"),
    )

    lti_1p3_tool_public_key = models.TextField(
        "LTI 1.3 Tool Public Key",
        blank=True,
        help_text='This is the LTI Tool\'s public key. This should be provided by the LTI Tool. '
                  'One of either lti_1p3_tool_public_key or lti_1p3_tool_keyset_url must not be blank.'
    )

    lti_1p3_tool_keyset_url = models.CharField(
        "LTI 1.3 Tool Keyset URL",
        max_length=500,
        blank=True,
        help_text='This is the LTI Tool\'s JWK (JSON Web Key) Keyset (JWKS) URL. This should be provided by the LTI '
                  'Tool. One of either lti_1p3_tool_public_key or lti_1p3_tool_keyset_url must not be blank.'
    )

    # Catalog metadata; all optional so that a converted passport keeps its history.
    description = models.TextField(_("Description"), blank=True)
    version = models.CharField(_("LTI Version"), max_length=10, choices=LTI_VERSION_CHOICES, null=True, blank=True)
    context_type = models.CharField(
        _("Context type"),
        max_length=20,
        choices=[
            ('course', _('Course')),
            ('organization', _('Organization')),
            ('site', _('Site')),
        ],
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(
        _("Active"),
        default=True,
        help_text=_("Inactive configurations cannot be linked to new placements or used by existing ones."),
    )

    # LTI 1.1 connection and credentials.
    lti_1p1_launch_url = models.CharField(_("LTI 1.1 Launch URL"), max_length=255, null=True, blank=True)
    lti_1p1_client_key = models.CharField(max_length=255, null=True, blank=True)
    lti_1p1_client_secret = models.CharField(max_length=255, null=True, blank=True)

    # LTI 1.3 tool connection and immutable registration identity.
    lti_1p3_launch_url = models.CharField(_("LTI 1.3 Launch URL"), max_length=255, null=True, blank=True)
    lti_1p3_oidc_url = models.CharField(
        _("LTI 1.3 OpenID Connect (OIDC) Login URL"), max_length=255, null=True, blank=True,
    )
    lti_1p3_redirect_uris = models.JSONField(_("LTI 1.3 Redirect URIs"), default=list, blank=True)
    lti_1p3_deployment_id = models.CharField(_("LTI 1.3 Deployment ID"), max_length=255, null=True, blank=True)
    lti_1p3_tool_key_mode = models.CharField(
        _("LTI 1.3 Tool Key Mode"),
        max_length=20,
        choices=[('public_key', _('Public Key')), ('keyset_url', _('Keyset URL'))],
        null=True,
        blank=True,
    )

    # Shared LTI Advantage service settings.
    lti_advantage_deep_linking_enabled = models.BooleanField(_("Enable LTI Advantage Deep Linking"), default=False)
    lti_advantage_deep_linking_launch_url = models.CharField(
        _("LTI Advantage Deep Linking launch URL"), max_length=225, blank=True, default='',
    )
    lti_advantage_ags_mode = models.CharField(
        _("LTI Advantage Assignment and Grade Services Mode"),
        max_length=20,
        choices=[
            ('disabled', _('Disabled')),
            ('declarative', _('Allow tools to submit grades only (declarative)')),
            ('programmatic', _('Allow tools to manage and submit grade (programmatic)')),
        ],
        default='declarative',
    )
    lti_advantage_enable_nrps = models.BooleanField(
        _("Enable LTI Advantage Names and Role Provisioning Services"), default=False,
    )

    # Shared placement defaults; placements and placement-specific data are not stored here.
    display_name = models.CharField(_("Display Name"), max_length=255, default='LTI Consumer')
    enable_grading = models.BooleanField(_("Enable grading"), default=False)
    grade_weight = models.FloatField(_("Grade Weight"), default=1.0, validators=[MinValueValidator(0)])
    accept_grades_after_due_date = models.BooleanField(_("Accept grades after due date"), default=True)
    open_tool_in = models.CharField(
        _("Open tool in"),
        max_length=20,
        choices=[('iframe', _('Inline')), ('modal', _('Modal')), ('new_window', _('New Window'))],
        default='iframe',
    )
    inline_height = models.IntegerField(_("Inline Height (px)"), default=800)
    modal_height = models.IntegerField(_("Modal Height (%)"), default=80)
    modal_width = models.IntegerField(_("Modal Width (%)"), default=80)
    launch_button_text = models.CharField(_("Launch Button Text"), max_length=255, blank=True, default='')
    send_extra_parameters = models.BooleanField(_("Send extra parameters"), default=False)
    custom_parameters = models.JSONField(_("Custom Parameters"), default=list, blank=True)

    # Privacy selections and external-tool visibility; staff choices, never learner data.
    pii_share_username = models.BooleanField(default=False)
    pii_share_full_name = models.BooleanField(default=False)
    pii_share_email = models.BooleanField(default=False)
    data_sharing_notice = models.TextField(blank=True, default='')
    require_user_confirmation = models.BooleanField(default=True)
    hide_external_tool = models.BooleanField(default=False)

    created_at = models.DateTimeField(_("Created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated at"), auto_now=True)

    def generate_lti_1p3_keys_if_missing(self):
        """
        Generate LTI 1.3 RSA256 keys if missing.

        If either the public or private key are missing, regenerate them.
        The LMS provides a keyset endpoint, so key rotations don't cause any issues
        for LTI launches (as long as they have a different kid).
        """
        # Generate new private key if not present
        if not self.lti_1p3_internal_private_key:
            # Private key
            private_key = RSA.generate(2048)
            self.lti_1p3_internal_private_key_id = str(uuid.uuid4())
            self.lti_1p3_internal_private_key = private_key.export_key('PEM').decode('utf-8')

            # Clear public key if any to allow regeneration
            # in the code below
            self.lti_1p3_internal_public_jwk = ''

        if not self.lti_1p3_internal_public_jwk:
            # Public key
            key_handler = PlatformKeyHandler(
                key_pem=self.lti_1p3_internal_private_key,
                kid=self.lti_1p3_internal_private_key_id,
            )
            self.lti_1p3_internal_public_jwk = json.dumps(
                key_handler.get_public_jwk()
            )

        # Doesn't do anything if model didn't change
        self.save()

    def get_runtime_identity(self):
        """Return the stored registration material a runtime request needs.

        A registration is usable only when its stored client ID, signing key pair and one
        tool key source are present and consistent. Existing rows are never repaired: a
        missing or invalid value denies the request instead of generating or rotating
        keys. Launch, presentation and grading settings are not part of this check.
        """
        if self.version != self.LTI_1P3:
            raise ReusableConfigurationUnavailable(
                "Only an LTI 1.3 registration can serve a launch or a token."
            )
        if not self.lti_1p3_client_id:
            raise ReusableConfigurationUnavailable("The registration has no client ID.")
        if not self.lti_1p3_internal_private_key or not self.lti_1p3_internal_private_key_id:
            raise ReusableConfigurationUnavailable("The registration has no signing key.")
        if not self.lti_1p3_tool_public_key and not self.lti_1p3_tool_keyset_url:
            raise ReusableConfigurationUnavailable("The registration has no tool key source.")

        return RuntimeIdentity(
            client_id=self.lti_1p3_client_id,
            deployment_id=self.lti_1p3_deployment_id or "1",
            private_key=self.lti_1p3_internal_private_key,
            private_key_id=self.lti_1p3_internal_private_key_id,
            public_jwk=_validated_public_jwk(
                self.lti_1p3_internal_private_key,
                self.lti_1p3_internal_private_key_id,
                self.lti_1p3_internal_public_jwk,
            ),
            tool_public_key=self.lti_1p3_tool_public_key,
            tool_keyset_url=self.lti_1p3_tool_keyset_url,
        )

    def __str__(self):
        return f'ReusableLtiConfiguration: {self.name} - {self.passport_id}'

    def clean(self):
        """Check tool-key mode/value consistency, when either is present.

        Legacy, incomplete and LTI 1.1 rows may legitimately carry no key material and no
        mode, so all-absent values are valid here.
        """
        if self.lti_1p3_tool_key_mode == 'public_key' and not self.lti_1p3_tool_public_key:
            raise ValidationError({
                "lti_1p3_tool_public_key": _("A public key is required in public-key mode."),
            })
        if self.lti_1p3_tool_key_mode == 'keyset_url' and not self.lti_1p3_tool_keyset_url:
            raise ValidationError({
                "lti_1p3_tool_keyset_url": _("A keyset URL is required in keyset-URL mode."),
            })

    class Meta:
        app_label = 'lti_consumer'
        verbose_name = _("Reusable LTI configuration")
        verbose_name_plural = _("Reusable LTI configurations")
        constraints = [
            # Converted rows may carry no context until one is assigned (Global Staff only).
            models.CheckConstraint(
                condition=(
                    models.Q(context_type__isnull=True) |
                    models.Q(context_type__in=('course', 'organization', 'site'))
                ),
                name='reusable_context_type_valid',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(context_type__isnull=True) |
                    models.Q(context_type='site', context_key='') |
                    (
                        models.Q(context_type__in=('course', 'organization')) &
                        models.Q(context_key__isnull=False) &
                        ~models.Q(context_key='')
                    )
                ),
                name='reusable_context_key_shape',
            ),
        ]
        indexes = [models.Index(fields=('context_type', 'context_key'), name='reusable_context_lookup')]


class LtiConfiguration(models.Model):
    """
    Model to store LTI Configuration for LTI 1.1 and 1.3.

    This models stores references (Usage Keys) and returns LTI
    configuration data fetching them from XBlock fields.

    With the implementation of
    https://github.com/openedx/xblock-lti-consumer/blob/master/docs/decisions/0001-lti-extensions-plugin.rst
    this model will store all LTI configuration values as a formatted JSON.

    .. no_pii:
    """
    # LTI Version
    LTI_1P1 = 'lti_1p1'
    LTI_1P3 = 'lti_1p3'
    LTI_VERSION_CHOICES = [
        (LTI_1P1, 'LTI 1.1'),
        (LTI_1P3, 'LTI 1.3 (with LTI Advantage Support)'),
    ]
    version = models.CharField(
        max_length=10,
        choices=LTI_VERSION_CHOICES,
        default=LTI_1P1,
    )

    # Configuration storage
    # Initally, this only supported the configuration
    # stored on the block. Now it has been expanded to
    # enable storing LTI configuration in the model itself or in an external
    # configuration service fetchable using openedx-filters
    CONFIG_ON_XBLOCK = 'CONFIG_ON_XBLOCK'
    CONFIG_ON_DB = 'CONFIG_ON_DB'
    CONFIG_EXTERNAL = 'CONFIG_EXTERNAL'
    CONFIG_STORE_CHOICES = [
        (CONFIG_ON_XBLOCK, _('Configuration Stored on XBlock fields')),
        (CONFIG_ON_DB, _('Configuration Stored on this model')),
        (CONFIG_EXTERNAL, _('Configuration Stored on external service')),
    ]
    config_store = models.CharField(
        max_length=255,
        choices=CONFIG_STORE_CHOICES,
        default=CONFIG_ON_XBLOCK,
    )

    # ID of the configuration if the configuration is obtained from the
    # external service using filters
    external_id = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    # A secondary ID for this configuration that can be used in URLs without leaking primary id.
    config_id = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)

    # Block location where the configuration is stored.
    location = UsageKeyField(
        max_length=255,
        db_index=True,
        null=True,
        blank=True,
        # Duplicate fails if not unique.
        unique=True,
    )

    # This is where the configuration is stored in the model if stored on this model.
    lti_config = JSONField(
        null=False,
        blank=True,
        default=dict,
        help_text=_("LTI configuration data.")
    )

    # LTI 1.1 Related variables
    lti_1p1_launch_url = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("The URL of the external tool that initiates the launch.")
    )
    lti_1p1_client_key = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Client key provided by the LTI tool provider.")
    )

    lti_1p1_client_secret = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Client secret provided by the LTI tool provider.")
    )

    # LTI 1.3 Related variables
    lti_1p3_passport = models.ForeignKey(
        Lti1p3Passport,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    reusable_configuration = models.ForeignKey(
        ReusableLtiConfiguration,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )

    lti_1p3_oidc_url = models.CharField(
        'LTI 1.3 OpenID Connect (OIDC) Login URL',
        max_length=255,
        blank=True,
        help_text='This is the OIDC third-party initiated login endpoint URL in the LTI 1.3 flow, '
                  'which should be provided by the LTI Tool.'
    )

    lti_1p3_launch_url = models.CharField(
        'LTI 1.3 Launch URL',
        max_length=255,
        blank=True,
        help_text='This is the LTI launch URL, otherwise known as the target_link_uri. '
                  'It represents the LTI resource to launch to or load in the second leg of the launch flow, '
                  'when the resource is actually launched or loaded.'
    )

    lti_1p3_redirect_uris = models.JSONField(
        "LTI 1.3 Redirect URIs",
        default=list,
        blank=True,
        help_text="Valid urls the Tool may request us to redirect the id token to. The redirect uris "
                  "are often the same as the launch url/deep linking url so if this field is "
                  "empty, it will use them as the default. If you need to use different redirect "
                  "uri's, enter them here. If you use this field you must enter all valid redirect "
                  "uri's the tool may request."
    )

    # LTI 1.3 Advantage Related Variables
    lti_advantage_enable_nrps = models.BooleanField(
        "Enable LTI Advantage Names and Role Provisioning Services",
        default=False,
        help_text='Enable LTI Advantage Names and Role Provisioning Services.',
    )

    lti_advantage_deep_linking_enabled = models.BooleanField(
        "Enable LTI Advantage Deep Linking",
        default=False,
        help_text='Enable LTI Advantage Deep Linking.',
    )

    lti_advantage_deep_linking_launch_url = models.CharField(
        "LTI Advantage Deep Linking launch URL",
        max_length=225,
        blank=True,
        help_text='This is the LTI Advantage Deep Linking launch URL. If the LTI Tool does not provide one, '
                  'use the same value as lti_1p3_launch_url.'
    )

    LTI_ADVANTAGE_AGS_DISABLED = 'disabled'
    LTI_ADVANTAGE_AGS_DECLARATIVE = 'declarative'
    LTI_ADVANTAGE_AGS_PROGRAMMATIC = 'programmatic'
    LTI_ADVANTAGE_AGS_CHOICES = [
        (LTI_ADVANTAGE_AGS_DISABLED, 'Disabled'),
        (LTI_ADVANTAGE_AGS_DECLARATIVE, 'Allow tools to submit grades only (declarative)'),
        (LTI_ADVANTAGE_AGS_PROGRAMMATIC, 'Allow tools to manage and submit grade (programmatic)')
    ]
    lti_advantage_ags_mode = models.CharField(
        "LTI Advantage Assignment and Grade Services Mode",
        max_length=20,
        choices=LTI_ADVANTAGE_AGS_CHOICES,
        default=LTI_ADVANTAGE_AGS_DECLARATIVE,
        help_text='Enable LTI Advantage Assignment and Grade Services and select the functionality enabled for LTI '
                  'tools. The "declarative" mode (default) will provide a tool with a LineItem created from the '
                  'XBlock settings, while the "programmatic" one will allow tools to manage, create and link the '
                  'grades.'
    )

    # LTI Proctoring Service Related Variables
    lti_1p3_proctoring_enabled = models.BooleanField(
        "Enable LTI Proctoring Services",
        default=False,
        help_text='Enable LTI Proctoring Services',
    )

    def clean(self):
        if self.config_store == self.CONFIG_ON_XBLOCK and self.location is None:
            raise ValidationError({
                "config_store": _("LTI Configuration stores on XBlock needs a block location set."),
            })
        if self.config_store == self.CONFIG_EXTERNAL and not EXTERNAL_ID_REGEX.match(str(self.external_id)):
            raise ValidationError({
                "config_store": _(
                    'LTI Configuration using reusable configuration needs a external ID in "x:y" format.',
                ),
            })
        if self.version == self.LTI_1P3 and self.config_store == self.CONFIG_ON_DB and not self.reusable_configuration:
            raise ValidationError({
                "config_store": _('LTI Configuration for 1.3 requires a reusable configuration to be set.'),
            })
        if (self.version == self.LTI_1P3 and self.config_store in [self.CONFIG_ON_XBLOCK, self.CONFIG_EXTERNAL] and
                self.lti_1p3_proctoring_enabled):
            raise ValidationError({
                "config_store": _("CONFIG_ON_XBLOCK and CONFIG_EXTERNAL are not supported for "
                                  "LTI 1.3 Proctoring Services."),
            })
        try:
            consumer = self.get_lti_consumer()
        except (NotImplementedError, ReusableConfigurationUnavailable):
            consumer = None
        if consumer is None:
            raise ValidationError(_("Invalid LTI configuration."))

    @function_trace('lti_consumer.models.LtiConfiguration.sync_configurations')
    def sync_configurations(self):
        """Syncronize main/children configurations.

        This method will synchronize the field values of main/children configurations.
        On a configuration with a CCX location, it will copy the values from the main course configuration,
        otherwise, it will try to query any children configuration and update their fields using
        the current configuration values.
        """
        EXCLUDED_FIELDS = ['id', 'config_id', 'location', 'external_config']

        if isinstance(self.location, CCXBlockUsageLocator):
            # Query main configuration using main location.
            main_config = LtiConfiguration.objects.filter(location=self.location.to_block_locator()).first()
            # Copy fields from main configuration.
            for field in model_to_dict(main_config, EXCLUDED_FIELDS).items():
                setattr(self, field[0], field[1])
        else:
            try:
                # Query child CCX configurations using location block ID and CCX namespace.
                child_configs = LtiConfiguration.objects.filter(
                    location__endswith=str(self.location).split('@')[-1],
                ).filter(
                    location__startswith=CCXBlockUsageLocator.CANONICAL_NAMESPACE,
                ).exclude(id=self.pk)
                # Copy fields to child CCX configurations.
                child_configs.update(**model_to_dict(self, EXCLUDED_FIELDS))
            except IndexError:
                log.exception(
                    f'Failed to query children CCX LTI configurations: '
                    f'Failed to parse main LTI configuration location: {self.location}',
                )

    def resolve_reusable_configuration(self, version=None):
        """
        Return the reusable configuration bound to this placement, binding one if absent.

        The binding is authoritative: a placement that already points at a catalog row is
        returned unchanged, so a later edit never re-derives identity from another row.
        Otherwise the UUID authored on the block is reused when the catalog still holds
        that row, including rows no placement points at yet, and only a miss creates a
        new row from the block's authoring state.
        """
        configuration = self.reusable_configuration
        if configuration is not None:
            return configuration

        block = compat.load_enough_xblock(self.location) if self.location else None
        block_passport_id = getattr(block, 'lti_1p3_passport_id', None) if block else None
        defaults = {
            'name': f"Configuration of {block.display_name}" if block else None,
            'context_key': block.context_id if block else None,
            'version': self.version if version is None else version,
        }
        if block:
            defaults['lti_1p3_tool_public_key'] = str(block.lti_1p3_tool_public_key or '')
            defaults['lti_1p3_tool_keyset_url'] = str(block.lti_1p3_tool_keyset_url or '')

        # The persisted UUID is the lookup key: a concurrent first use shares the row the
        # other request created instead of racing a second one into existence.
        configuration, created = ReusableLtiConfiguration.objects.get_or_create(
            passport_id=block_passport_id or uuid.uuid4(),
            defaults=defaults,
        )
        if created:
            log.info("Created reusable LTI configuration %s for %s", configuration, self)
            if configuration.version == ReusableLtiConfiguration.LTI_1P3:
                # A creator seeds its own signing material once; readers never repair it.
                configuration.generate_lti_1p3_keys_if_missing()

        if self.pk is None:
            # The row cannot be linked before it exists; the in-memory link is saved with it.
            self.reusable_configuration = configuration
            return configuration

        # Write the authoritative link without re-entering the post_save receiver.
        LtiConfiguration.objects.filter(pk=self.pk).update(reusable_configuration=configuration)
        self.refresh_from_db()
        return configuration

    def get_runtime_identity(self, version=None):
        """Return validated registration material for this placement's runtime identity."""
        return self.resolve_reusable_configuration(version=version).get_runtime_identity()

    def save(self, *args, **kwargs):
        self.sync_configurations()
        super().save(*args, **kwargs)

    @property
    def passport_id(self):
        """
        Return the reusable configuration's passport ID for this placement.
        """
        return self.resolve_reusable_configuration().passport_id

    @property
    def lti_1p3_private_key(self):
        """
        Return the platform's private key used in LTI 1.3 authentication flows.
        """
        return self.get_runtime_identity().private_key

    @property
    def lti_1p3_private_key_id(self):
        """
        Return the platform's private key ID used in LTI 1.3 authentication flows.
        """
        return self.get_runtime_identity().private_key_id

    @property
    def lti_1p3_public_jwk(self):
        """
        Return the platform's public keys used in LTI 1.3 authentication flows.
        """
        return self.get_runtime_identity().public_jwk

    @property
    def lti_1p3_client_id(self):
        """
        Return the client ID stored on the reusable configuration.
        """
        return self.get_runtime_identity().client_id

    @property
    def lti_1p3_deployment_id(self):
        """
        Return the stored deployment ID, or the historical `"1"` when it is unset.

        Copied registrations keep the single deployed tool registration they were launched
        with; configurations created through the API store their own deployment ID.
        """
        return self.get_runtime_identity().deployment_id

    @property
    def lti_1p3_tool_keyset_url(self):
        """
        Return the tool keyset URL stored on the reusable configuration.
        """
        return self.get_runtime_identity().tool_keyset_url

    @property
    def lti_1p3_tool_public_key(self):
        """
        Return the tool public key stored on the reusable configuration.
        """
        return self.get_runtime_identity().tool_public_key

    @cached_property
    def external_config(self):
        """
        Return the external resuable configuration.
        """
        return get_external_config_from_filter({}, self.external_id)

    def _get_lti_1p1_consumer(self):
        """
        Return a class of LTI 1.1 consumer.
        """
        # If LTI configuration is stored in the XBlock.
        if self.config_store == self.CONFIG_ON_XBLOCK:
            block = compat.load_enough_xblock(self.location)
            key, secret = block.lti_provider_key_secret
            launch_url = block.launch_url
        elif self.config_store == self.CONFIG_EXTERNAL:
            key = self.external_config.get("lti_1p1_client_key")
            secret = self.external_config.get("lti_1p1_client_secret")
            launch_url = self.external_config.get("lti_1p1_launch_url")
        else:
            key = self.lti_1p1_client_key
            secret = self.lti_1p1_client_secret
            launch_url = self.lti_1p1_launch_url

        return LtiConsumer1p1(launch_url, key, secret)

    def get_lti_advantage_ags_mode(self):
        """
        Return LTI 1.3 Advantage Assignment and Grade Services mode.
        """
        if self.config_store == self.CONFIG_ON_DB:
            return self.lti_advantage_ags_mode
        elif self.config_store == self.CONFIG_EXTERNAL:
            return self.external_config.get('lti_advantage_ags_mode')
        else:
            block = compat.load_enough_xblock(self.location)
            return block.lti_advantage_ags_mode

    def get_lti_advantage_deep_linking_enabled(self):
        """
        Return whether LTI 1.3 Advantage Deep Linking is enabled.
        """
        if self.config_store == self.CONFIG_ON_DB:
            return self.lti_advantage_deep_linking_enabled
        elif self.config_store == self.CONFIG_EXTERNAL:
            return self.external_config.get('lti_advantage_deep_linking_enabled')
        else:
            block = compat.load_enough_xblock(self.location)
            return block.lti_advantage_deep_linking_enabled

    def get_lti_advantage_deep_linking_launch_url(self):
        """
        Return the LTI 1.3 Advantage Deep Linking launch URL.
        """
        if self.config_store == self.CONFIG_ON_DB:
            return self.lti_advantage_deep_linking_launch_url
        elif self.config_store == self.CONFIG_EXTERNAL:
            return self.external_config.get('lti_advantage_deep_linking_launch_url')
        else:
            block = compat.load_enough_xblock(self.location)
            return block.lti_advantage_deep_linking_launch_url

    def get_lti_advantage_nrps_enabled(self):
        """
        Return whether LTI 1.3 Advantage Names and Role Provisioning Services is enabled.
        """
        if self.config_store == self.CONFIG_ON_DB:
            return self.lti_advantage_enable_nrps
        elif self.config_store == self.CONFIG_EXTERNAL:
            return self.external_config.get('lti_advantage_enable_nrps')
        else:
            block = compat.load_enough_xblock(self.location)
            return block.lti_1p3_enable_nrps

    def _setup_lti_1p3_ags(self, consumer):
        """
        Set up LTI 1.3 Advantage Assigment and Grades Services.
        """

        try:
            lti_advantage_ags_mode = self.get_lti_advantage_ags_mode()
        except NotImplementedError as exc:
            log.exception("Error setting up LTI 1.3 Advantage Assignment and Grade Services: %s", exc)
            return

        if lti_advantage_ags_mode == self.LTI_ADVANTAGE_AGS_DISABLED:
            log.info('LTI Advantage AGS is disabled for %s', self)
            return

        lineitem = self.ltiagslineitem_set.first()

        # If using the declarative approach, we should create a LineItem if it
        # doesn't exist. This is because on this mode the tool is not able to create
        # and manage lineitems using the AGS endpoints.
        if not lineitem and lti_advantage_ags_mode == self.LTI_ADVANTAGE_AGS_DECLARATIVE:
            try:
                block = compat.load_enough_xblock(self.location)
            except ValueError:  # There is no location to load the block
                block = None

            if block:
                default_values = {
                    'resource_id': self.location,
                    'score_maximum': block.weight,
                    'label': block.display_name,
                }
                if hasattr(block, 'start'):
                    default_values['start_date_time'] = block.start

                if hasattr(block, 'due'):
                    default_values['end_date_time'] = block.due
            else:
                # TODO find a way to make these defaults more sensible
                default_values = {
                    'resource_id': self.location,
                    'score_maximum': 100,
                    'label': 'LTI Consumer at ' + str(self.location)
                }

            # create LineItem if there is none for current lti configuration
            lineitem = LtiAgsLineItem.objects.create(
                lti_configuration=self,
                resource_link_id=self.location,
                **default_values
            )

        consumer.enable_ags(
            lineitems_url=get_lti_ags_lineitems_url(self.id),
            lineitem_url=get_lti_ags_lineitems_url(self.id, lineitem.id) if lineitem else None,
            allow_programmatic_grade_interaction=(
                lti_advantage_ags_mode == self.LTI_ADVANTAGE_AGS_PROGRAMMATIC
            )
        )

    def _setup_lti_1p3_deep_linking(self, consumer):
        """
        Set up LTI 1.3 Advantage Deep Linking.
        """
        try:
            if self.get_lti_advantage_deep_linking_enabled():
                consumer.enable_deep_linking(
                    self.get_lti_advantage_deep_linking_launch_url(),
                    get_lti_deeplinking_response_url(self.id),
                )
        except NotImplementedError as exc:
            log.exception("Error setting up LTI 1.3 Advantage Deep Linking: %s", exc)

    def _setup_lti_1p3_nrps(self, consumer):
        """
        Set up LTI 1.3 Advantage Names and Role Provisioning Services.
        """
        try:
            if self.get_lti_advantage_nrps_enabled():
                consumer.enable_nrps(get_lti_nrps_context_membership_url(self.id))
        except NotImplementedError as exc:
            log.exception("Error setting up LTI 1.3 Advantage Names and Role Provisioning Services: %s", exc)

    def _get_lti_1p3_consumer(self):
        """
        Return a class of LTI 1.3 consumer.

        Uses the `config_store` variable to determine where to look for the launch
        and presentation settings. Identity, signing keys, tool keys, client ID and the
        deployment ID always come from the reusable configuration bound to this
        placement; there is no fallback to the retained passport table or the block.
        """
        consumer_class = LtiAdvantageConsumer
        # LTI Proctoring Services is not currently supported for CONFIG_ON_XBLOCK or CONFIG_EXTERNAL.
        # NOTE: This currently prevents an LTI Consumer from supporting both the LTI 1.3 proctoring feature and the LTI
        # Advantage services. We plan to address this. Follow this issue:
        # https://github.com/openedx/xblock-lti-consumer/issues/303.
        if self.lti_1p3_proctoring_enabled and self.config_store == self.CONFIG_ON_DB:
            consumer_class = LtiProctoringConsumer

        if self.config_store == self.CONFIG_ON_XBLOCK:
            block = compat.load_enough_xblock(self.location)
            identity = self.get_runtime_identity()

            consumer = consumer_class(
                iss=get_lti_api_base(),
                lti_oidc_url=block.lti_1p3_oidc_url,
                lti_launch_url=block.lti_1p3_launch_url,
                client_id=identity.client_id,
                deployment_id=identity.deployment_id,
                rsa_key=identity.private_key,
                rsa_key_id=identity.private_key_id,
                # Registered redirect uris
                redirect_uris=self.get_lti_1p3_redirect_uris(),
                # LTI 1.3 Tool key/keyset url
                tool_key=identity.tool_public_key,
                tool_keyset_url=identity.tool_keyset_url,
            )
        elif self.config_store == self.CONFIG_ON_DB:
            identity = self.get_runtime_identity()

            consumer = consumer_class(
                iss=get_lti_api_base(),
                lti_oidc_url=self.lti_1p3_oidc_url,
                lti_launch_url=self.lti_1p3_launch_url,
                client_id=identity.client_id,
                deployment_id=identity.deployment_id,
                rsa_key=identity.private_key,
                rsa_key_id=identity.private_key_id,
                # Registered redirect uris
                redirect_uris=self.get_lti_1p3_redirect_uris(),
                # LTI 1.3 Tool key/keyset url
                tool_key=identity.tool_public_key,
                tool_keyset_url=identity.tool_keyset_url,
            )
        elif self.config_store == self.CONFIG_EXTERNAL:
            lti_launch_url = self.external_config.get('lti_1p3_launch_url')

            if external_multiple_launch_urls_enabled(self.location.course_key):
                block = compat.load_enough_xblock(self.location)

                lti_launch_url = block.lti_1p3_launch_url or lti_launch_url

            consumer = consumer_class(
                iss=get_lti_api_base(),
                lti_oidc_url=self.external_config.get('lti_1p3_oidc_url'),
                lti_launch_url=lti_launch_url,
                client_id=self.external_config.get('lti_1p3_client_id'),
                deployment_id=self.external_config.get('lti_1p3_deployment_id', "1"),
                rsa_key=self.external_config.get('lti_1p3_private_key'),
                rsa_key_id=self.external_config.get('lti_1p3_private_key_id'),
                # Registered redirect uris
                redirect_uris=self.get_lti_1p3_redirect_uris(),
                tool_key=self.external_config.get('lti_1p3_tool_public_key'),
                tool_keyset_url=self.external_config.get('lti_1p3_tool_keyset_url'),
            )
        else:
            # This should not occur, but raise an error if self.config_store is not
            # CONFIG_ON_XBLOCK, CONFIG_ON_DB or CONFIG_EXTERNAL.
            raise NotImplementedError

        if isinstance(consumer, LtiAdvantageConsumer):
            self._setup_lti_1p3_ags(consumer)
            self._setup_lti_1p3_deep_linking(consumer)
            self._setup_lti_1p3_nrps(consumer)

        return consumer

    def get_effective_version(self):
        """
        Return the LTI version stored by the runtime identity source of this placement.

        When ``config_store == CONFIG_EXTERNAL``, checks the external config
        for a ``version`` key and returns it.  Falls back to ``self.version``.

        Every other placement reads the stored version of its bound reusable
        configuration, which is the only place a version may come from. An unbound
        placement keeps its own version, and a bound row whose version is unassigned
        reports ``None`` so runtime gates deny it instead of guessing.
        """
        if self.config_store == self.CONFIG_EXTERNAL:
            ext_version = self.external_config.get('version')
            if ext_version is not None:
                return ext_version
            return self.version
        configuration = self.reusable_configuration
        if configuration is not None:
            return configuration.version
        return self.version

    @function_trace('lti_consumer.models.LtiConfiguration.get_lti_consumer')
    def get_lti_consumer(self):
        """
        Returns an instanced class of LTI 1.1 or 1.3 consumer.

        When using external config, the version from the external config
        takes priority over the locally stored version to avoid version
        mismatch crashes. An unassigned version refuses the request instead
        of silently serving the other version.
        """
        effective_version = self.get_effective_version()

        if effective_version is None:
            raise ReusableConfigurationUnavailable(
                f"LTI configuration {self.config_id} has no assigned LTI version."
            )

        configuration = self.reusable_configuration
        if (
            self.config_store != self.CONFIG_EXTERNAL and
            configuration is not None and
            self.version is not None and
            configuration.version is not None and
            self.version != configuration.version
        ):
            raise ReusableConfigurationUnavailable(
                "The placement LTI version does not match its reusable configuration."
            )

        if effective_version == self.LTI_1P3:
            return self._get_lti_1p3_consumer()

        return self._get_lti_1p1_consumer()

    def get_lti_1p3_redirect_uris(self):
        """
        Return pre-registered redirect uris or sensible defaults
        """
        if self.config_store == self.CONFIG_EXTERNAL:
            redirect_uris = self.external_config.get('lti_1p3_redirect_uris')
            launch_url = self.external_config.get('lti_1p3_launch_url')
            deep_link_launch_url = self.external_config.get('lti_advantage_deep_linking_launch_url')
        elif self.config_store == self.CONFIG_ON_DB:
            redirect_uris = self.lti_1p3_redirect_uris
            launch_url = self.lti_1p3_launch_url
            deep_link_launch_url = self.lti_advantage_deep_linking_launch_url
        else:
            block = compat.load_enough_xblock(self.location)
            redirect_uris = block.lti_1p3_redirect_uris
            launch_url = block.lti_1p3_launch_url
            deep_link_launch_url = block.lti_advantage_deep_linking_launch_url

        return choose_lti_1p3_redirect_uris(
            redirect_uris,
            launch_url,
            deep_link_launch_url
        )

    @property
    def pii_share_username(self):
        return self.lti_config.get('pii_share_username', False)     # pylint: disable=no-member

    @pii_share_username.setter
    def pii_share_username(self, value):
        self.lti_config['pii_share_username'] = value               # pylint: disable=unsupported-assignment-operation

    @property
    def pii_share_email(self):
        return self.lti_config.get('pii_share_email', False)        # pylint: disable=no-member

    @pii_share_email.setter
    def pii_share_email(self, value):
        self.lti_config['pii_share_email'] = value                  # pylint: disable=unsupported-assignment-operation

    def __str__(self):
        return f"[{self.config_store}] {self.version} - {self.location}"

    class Meta:
        app_label = 'lti_consumer'


class LtiAgsLineItem(models.Model):
    """
    Model to store LineItem data for LTI Assignments and Grades service.

    LTI-AGS Specification: https://www.imsglobal.org/spec/lti-ags/v2p0
    The platform MUST NOT modify the 'resourceId', 'resourceLinkId' and 'tag' values.

    Note: When implementing multi-tenancy support, this needs to be changed
    and be tied to a deployment ID, because each deployment should isolate
    it's resources.

    .. no_pii:
    """
    # LTI Configuration link
    # This ties the LineItem to each tool configuration
    # and allows easily retrieving LTI credentials for
    # API authentication.
    lti_configuration = models.ForeignKey(
        LtiConfiguration,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    # Tool resource identifier, not used by the LMS.
    resource_id = models.CharField(max_length=255, blank=True)

    # LMS Resource link
    # Must be the same as the one sent in the tool's LTI launch.
    # Each LineItem created by a tool should be specific to the
    # context from which it was created.
    # Currently it maps to a block using a usagekey
    resource_link_id = UsageKeyField(
        max_length=255,
        db_index=True,
        null=True,
        blank=True,
    )

    # Other LineItem attributes
    label = models.CharField(max_length=100)
    score_maximum = models.IntegerField()
    tag = models.CharField(max_length=50, blank=True)
    start_date_time = models.DateTimeField(blank=True, null=True)
    end_date_time = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return "{} - {}".format(
            self.resource_link_id,
            self.label,
        )

    class Meta:
        app_label = 'lti_consumer'


class LtiAgsScore(models.Model):
    """
    Model to store LineItem Score data for LTI Assignments and Grades service.

    LTI-AGS Specification: https://www.imsglobal.org/spec/lti-ags/v2p0
    Note: When implementing multi-tenancy support, this needs to be changed
    and be tied to a deployment ID, because each deployment should isolate
    it's resources.

    .. no_pii:
    """

    # LTI LineItem
    # This links the score to a specific line item
    line_item = models.ForeignKey(
        LtiAgsLineItem,
        on_delete=models.CASCADE,
        related_name='scores',
    )

    timestamp = models.DateTimeField()

    # All 'scoreGiven' and 'scoreMaximum' values MUST be positive numbers (including 0).
    score_given = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0)])
    score_maximum = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0)])
    comment = models.TextField(null=True, blank=True)

    # Activity Progress Choices
    INITIALIZED = 'Initialized'
    STARTED = 'Started'
    IN_PROGRESS = 'InProgress'
    SUBMITTED = 'Submitted'
    COMPLETED = 'Completed'

    ACTIVITY_PROGRESS_CHOICES = [
        (INITIALIZED, INITIALIZED),
        (STARTED, STARTED),
        (IN_PROGRESS, IN_PROGRESS),
        (SUBMITTED, SUBMITTED),
        (COMPLETED, COMPLETED),
    ]
    activity_progress = models.CharField(
        max_length=20,
        choices=ACTIVITY_PROGRESS_CHOICES
    )

    # Grading Progress Choices
    FULLY_GRADED = 'FullyGraded'
    PENDING = 'Pending'
    PENDING_MANUAL = 'PendingManual'
    FAILED = 'Failed'
    NOT_READY = 'NotReady'

    GRADING_PROGRESS_CHOICES = [
        (FULLY_GRADED, FULLY_GRADED),
        (PENDING, PENDING),
        (PENDING_MANUAL, PENDING_MANUAL),
        (FAILED, FAILED),
        (NOT_READY, NOT_READY),
    ]
    grading_progress = models.CharField(
        max_length=20,
        choices=GRADING_PROGRESS_CHOICES
    )

    user_id = models.CharField(max_length=255)

    def clean(self):
        super().clean()

        # 'scoreMaximum' is the denominator, so it has to be present and positive whenever
        # 'scoreGiven' is present.  'scoreGiven' is tested with `is not None` because 0 is
        # a valid grade; 'scoreMaximum' is tested for falsiness because both None and 0
        # are rejected.
        if self.score_given is not None and not self.score_maximum:
            raise ValidationError(
                {'score_maximum': 'must be a positive number when score_given is set'}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return "LineItem {line_item_id}: score {score_given} out of {score_maximum} - {grading_progress}".format(
            line_item_id=self.line_item.id,
            score_given=self.score_given,
            score_maximum=self.score_maximum,
            grading_progress=self.grading_progress
        )

    class Meta:
        app_label = 'lti_consumer'
        unique_together = (('line_item', 'user_id'),)


class LtiDlContentItem(models.Model):
    """
    Model to store Content Items for LTI Deep Linking service.

    LTI-DL Specification: https://www.imsglobal.org/spec/lti-dl/v2p0
    Content items are resources selected by instructor that should
    be displayed to students.

    .. no_pii:
    """
    # LTI Configuration link
    # This ties the LineItem to each tool configuration
    # and allows easily retrieving LTI credentials for
    # API authentication.
    lti_configuration = models.ForeignKey(
        LtiConfiguration,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    # Content Item Types
    # Values based on http://www.imsglobal.org/spec/lti-dl/v2p0#content-item-types
    # to make type matching easier.
    LINK = 'link'
    LTI_RESOURCE_LINK = 'ltiResourceLink'
    FILE = 'file'
    HTML_FRAGMENT = 'html'
    IMAGE = 'image'
    CONTENT_TYPE_CHOICES = [
        (LINK, 'Link to external resource'),
        (LTI_RESOURCE_LINK, 'LTI Resource Link'),
        (FILE, 'File'),
        (HTML_FRAGMENT, 'HTML Fragment'),
        (IMAGE, 'Image'),
    ]
    content_type = models.CharField(
        max_length=255,
        choices=CONTENT_TYPE_CHOICES,
    )

    # Content Item Attributes
    attributes = JSONField()

    def __str__(self):
        return "{}: {}".format(
            self.lti_configuration,
            self.content_type,
        )

    class Meta:
        app_label = 'lti_consumer'


class CourseAllowPIISharingInLTIFlag(ConfigurationModel):
    """
    Enables the sharing of PII via LTI for the specific course.

    Depending on where it's used, further action might be needed to actually
    enable sharing PII. For instance, in the LTI XBlock setting this flag
    will allow editing the "request username" and "request email" fields, which
    will also need to be set to actually share PII.

    .. no_pii:
    """
    KEY_FIELDS = ('course_id',)

    course_id = CourseKeyField(max_length=255, db_index=True)

    @classmethod
    def lti_access_to_learners_editable(cls, course_id: CourseKey, is_already_sharing_learner_info: bool) -> bool:
        """
        Looks at the currently active configuration model to determine whether
        the feature that enables editing of "request username" and "request email"
        fields of LTI consumer is available or not.

        Backwards Compatibility:
        Enable this feature for a course run who was sharing learner username/email
        in the past.

        Arguments:
            course_id (CourseKey): course id for which we need to check this configuration
            is_already_sharing_learner_info (bool): indicates whether LTI consumer is
            already sharing edX learner username/email.
        """
        course_specific_config = (CourseAllowPIISharingInLTIFlag.objects
                                  .filter(course_id=course_id)
                                  .order_by('-change_date')
                                  .first())

        if is_already_sharing_learner_info and not course_specific_config:
            CourseAllowPIISharingInLTIFlag.objects.create(course_id=course_id, enabled=True)
            return True

        return course_specific_config.enabled if course_specific_config else False

    def __str__(self):
        return (
            f"Course '{self.course_id}': "
            f"Edit LTI access to Learner information {'' if self.enabled else 'Not '}Enabled"
        )

    class Meta:
        # This model was moved from edx-platform, with intention of retaining existing data.
        # This is referencing the original table name.
        app_label = "lti_consumer"
        db_table = "xblock_config_courseeditltifieldsenabledflag"
