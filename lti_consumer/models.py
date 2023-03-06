"""
LTI configuration and linking models.
"""
import logging
import uuid
import json

from django.db import models
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError

from jsonfield import JSONField
from Cryptodome.PublicKey import RSA
from opaque_keys.edx.django.models import CourseKeyField, UsageKeyField
from opaque_keys.edx.keys import CourseKey
from config_models.models import ConfigurationModel
from django.utils.translation import gettext_lazy as _
from lti_consumer.filters import get_external_config_from_filter

# LTI 1.1
from lti_consumer.lti_1p1.consumer import LtiConsumer1p1
# LTI 1.3
from lti_consumer.lti_1p3.consumer import LtiAdvantageConsumer, LtiProctoringConsumer
from lti_consumer.lti_1p3.key_handlers import PlatformKeyHandler
from lti_consumer.plugin import compat
from lti_consumer.utils import (
    get_lti_api_base,
    get_lti_ags_lineitems_url,
    get_lti_deeplinking_response_url,
    get_lti_nrps_context_membership_url,
    choose_lti_1p3_redirect_uris,
)

log = logging.getLogger(__name__)


def generate_client_id():
    """
    Generates a random UUID string.
    """
    return str(uuid.uuid4())


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

    lti_1p3_tool_public_key = models.TextField(
        "LTI 1.3 Tool Public Key",
        blank=True,
        help_text='This is the LTI Tool\'s public key. This should be provided by the LTI Tool. '
                  'One of either lti_1p3_tool_public_key or lti_1p3_tool_keyset_url must not be blank.'
    )

    lti_1p3_tool_keyset_url = models.CharField(
        "LTI 1.3 Tool Keyset URL",
        max_length=255,
        blank=True,
        help_text='This is the LTI Tool\'s JWK (JSON Web Key) Keyset (JWKS) URL. This should be provided by the LTI '
                  'Tool. One of either lti_1p3_tool_public_key or lti_1p3_tool_keyset_url must not be blank.'
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
        if self.version == self.LTI_1P3 and self.config_store == self.CONFIG_ON_DB:
            if self.lti_1p3_tool_public_key == "" and self.lti_1p3_tool_keyset_url == "":
                raise ValidationError({
                    "config_store": _(
                        "LTI Configuration stored on the model for LTI 1.3 must have a value for one of "
                        "lti_1p3_tool_public_key or lti_1p3_tool_keyset_url."
                    ),
                })
        if (self.version == self.LTI_1P3 and self.config_store in [self.CONFIG_ON_XBLOCK, self.CONFIG_EXTERNAL] and
                self.lti_1p3_proctoring_enabled):
            raise ValidationError({
                "config_store": _("CONFIG_ON_XBLOCK and CONFIG_EXTERNAL are not supported for "
                                  "LTI 1.3 Proctoring Services."),
            })
        try:
            consumer = self.get_lti_consumer()
        except NotImplementedError:
            consumer = None
        if consumer is None:
            raise ValidationError(_("Invalid LTI configuration."))

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
            config = get_external_config_from_filter({}, self.external_id)
            key = config.get("lti_1p1_client_key")
            secret = config.get("lti_1p1_client_secret")
            launch_url = config.get("lti_1p1_launch_url")
        else:
            key = self.lti_1p1_client_key
            secret = self.lti_1p1_client_secret
            launch_url = self.lti_1p1_launch_url

        return LtiConsumer1p1(launch_url, key, secret)

    def get_lti_advantage_ags_mode(self):
        """
        Return LTI 1.3 Advantage Assignment and Grade Services mode.
        """
        if self.config_store == self.CONFIG_EXTERNAL:
            # TODO: Add support for CONFIG_EXTERNAL for LTI 1.3.
            raise NotImplementedError
        if self.config_store == self.CONFIG_ON_DB:
            return self.lti_advantage_ags_mode
        else:
            block = compat.load_enough_xblock(self.location)
            return block.lti_advantage_ags_mode

    def get_lti_advantage_deep_linking_enabled(self):
        """
        Return whether LTI 1.3 Advantage Deep Linking is enabled.
        """
        if self.config_store == self.CONFIG_EXTERNAL:
            # TODO: Add support for CONFIG_EXTERNAL for LTI 1.3.
            raise NotImplementedError("CONFIG_EXTERNAL is not supported for LTI 1.3 Advantage services: %s")
        if self.config_store == self.CONFIG_ON_DB:
            return self.lti_advantage_deep_linking_enabled
        else:
            block = compat.load_enough_xblock(self.location)
            return block.lti_advantage_deep_linking_enabled

    def get_lti_advantage_deep_linking_launch_url(self):
        """
        Return the LTI 1.3 Advantage Deep Linking launch URL.
        """
        if self.config_store == self.CONFIG_EXTERNAL:
            # TODO: Add support for CONFIG_EXTERNAL for LTI 1.3.
            raise NotImplementedError("CONFIG_EXTERNAL is not supported for LTI 1.3 Advantage services: %s")
        if self.config_store == self.CONFIG_ON_DB:
            return self.lti_advantage_deep_linking_launch_url
        else:
            block = compat.load_enough_xblock(self.location)
            return block.lti_advantage_deep_linking_launch_url

    def get_lti_advantage_nrps_enabled(self):
        """
        Return whether LTI 1.3 Advantage Names and Role Provisioning Services is enabled.
        """
        if self.config_store == self.CONFIG_EXTERNAL:
            # TODO: Add support for CONFIG_EXTERNAL for LTI 1.3.
            raise NotImplementedError("CONFIG_EXTERNAL is not supported for LTI 1.3 Advantage services: %s")
        if self.config_store == self.CONFIG_ON_DB:
            return self.lti_advantage_enable_nrps
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

        Uses the `config_store` variable to determine where to
        look for the configuration and instance the class.
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

            consumer = consumer_class(
                iss=get_lti_api_base(),
                lti_oidc_url=block.lti_1p3_oidc_url,
                lti_launch_url=block.lti_1p3_launch_url,
                client_id=self.lti_1p3_client_id,
                # Deployment ID hardcoded to 1 since
                # we're not using multi-tenancy.
                deployment_id="1",
                # XBlock Private RSA Key
                rsa_key=self.lti_1p3_private_key,
                rsa_key_id=self.lti_1p3_private_key_id,
                # Registered redirect uris
                redirect_uris=self.get_lti_1p3_redirect_uris(),
                # LTI 1.3 Tool key/keyset url
                tool_key=block.lti_1p3_tool_public_key,
                tool_keyset_url=block.lti_1p3_tool_keyset_url,
            )
        elif self.config_store == self.CONFIG_ON_DB:
            consumer = consumer_class(
                iss=get_lti_api_base(),
                lti_oidc_url=self.lti_1p3_oidc_url,
                lti_launch_url=self.lti_1p3_launch_url,
                client_id=self.lti_1p3_client_id,
                # Deployment ID hardcoded to 1 since
                # we're not using multi-tenancy.
                deployment_id="1",
                # XBlock Private RSA Key
                rsa_key=self.lti_1p3_private_key,
                rsa_key_id=self.lti_1p3_private_key_id,
                # Registered redirect uris
                redirect_uris=self.get_lti_1p3_redirect_uris(),
                # LTI 1.3 Tool key/keyset url
                tool_key=self.lti_1p3_tool_public_key,
                tool_keyset_url=self.lti_1p3_tool_keyset_url,
            )
        else:
            # This should not occur, but raise an error if self.config_store is not CONFIG_ON_XBLOCK
            # or CONFIG_ON_DB.
            raise NotImplementedError

        if isinstance(consumer, LtiAdvantageConsumer):
            self._setup_lti_1p3_ags(consumer)
            self._setup_lti_1p3_deep_linking(consumer)
            self._setup_lti_1p3_nrps(consumer)

        return consumer

    def get_lti_consumer(self):
        """
        Returns an instanced class of LTI 1.1 or 1.3 consumer.
        """
        if self.version == self.LTI_1P3:
            return self._get_lti_1p3_consumer()

        return self._get_lti_1p1_consumer()

    def get_lti_1p3_redirect_uris(self):
        """
        Return pre-registered redirect uris or sensible defaults
        """
        if self.config_store == self.CONFIG_EXTERNAL:
            # TODO: Add support for CONFIG_EXTERNAL for LTI 1.3.
            raise NotImplementedError

        if self.config_store == self.CONFIG_ON_DB:
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
    resource_id = models.CharField(max_length=100, blank=True)

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

        # 'scoreMaximum' represents the denominator and MUST be present when 'scoreGiven' is present
        if self.score_given and self.score_maximum is None:
            raise ValidationError({'score_maximum': 'cannot be unset when score_given is set'})

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
        db_table = "xblock_config_courseeditltifieldsenabledflag"
