"""
LTI configuration and linking models.
"""
import uuid
import json
from django.db import models
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError

from opaque_keys.edx.django.models import UsageKeyField
from Cryptodome.PublicKey import RSA

# LTI 1.1
from lti_consumer.lti_1p1.consumer import LtiConsumer1p1
# LTI 1.3
from lti_consumer.lti_1p3.consumer import LtiAdvantageConsumer
from lti_consumer.lti_1p3.key_handlers import PlatformKeyHandler
from lti_consumer.plugin import compat
from lti_consumer.utils import (
    get_lms_base,
    get_lti_ags_lineitems_url,
)


def generate_client_id():
    """
    Generates a random UUID string.
    """
    return str(uuid.uuid4())


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
    https://github.com/edx/xblock-lti-consumer/blob/master/docs/decisions/0001-lti-extensions-plugin.rst
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
    # Initally, this only supports the configuration
    # stored on the block, but should be expanded to
    # enable storing LTI configuration in this model.
    CONFIG_ON_XBLOCK = 'CONFIG_ON_XBLOCK'
    CONFIG_STORE_CHOICES = [
        (CONFIG_ON_XBLOCK, 'Configuration Stored on XBlock fields'),
    ]
    config_store = models.CharField(
        max_length=255,
        choices=CONFIG_STORE_CHOICES,
        default=CONFIG_ON_XBLOCK,
    )

    # Block location where the configuration is stored.
    # In the future, the LTI configuration will be
    # stored in this model in a JSON field.
    location = UsageKeyField(
        max_length=255,
        db_index=True,
        null=True,
        blank=True,
    )

    # LTI 1.3 Related variables
    lti_1p3_internal_private_key = models.TextField(
        blank=True,
        help_text="Platform's generated Private key. Keep this value secret.",
    )

    lti_1p3_internal_private_key_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Platform's generated Private key ID",
    )

    lti_1p3_internal_public_jwk = models.TextField(
        blank=True,
        help_text="Platform's generated JWK keyset.",
    )

    lti_1p3_client_id = models.CharField(
        max_length=255,
        default=generate_client_id,
        help_text="Client ID used by LTI tool",
    )

    # Empty variable that'll hold the block once it's retrieved
    # from the modulestore or preloaded
    _block = None

    @property
    def block(self):
        """
        Return instance of block (either preloaded or directly from the modulestore).
        """
        block = getattr(self, '_block', None)
        if block is None:
            if self.location is None:
                raise ValueError("Block location not set, it's not possible to retrieve the block.")
            block = self._block = compat.load_block_as_anonymous_user(self.location)
        return block

    @block.setter
    def block(self, block):
        """
        Allows preloading the block instead of fetching it from the modulestore.
        """
        self._block = block

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
            key, secret = self.block.lti_provider_key_secret

            return LtiConsumer1p1(self.block.launch_url, key, secret)

        # There's no configuration stored locally, so throw
        # NotImplemented.
        raise NotImplementedError

    def _get_lti_1p3_consumer(self):
        """
        Return a class of LTI 1.3 consumer.

        Uses the `config_store` variable to determine where to
        look for the configuration and instance the class.
        """
        # If LTI configuration is stored in the XBlock.
        if self.config_store == self.CONFIG_ON_XBLOCK:
            consumer = LtiAdvantageConsumer(
                iss=get_lms_base(),
                lti_oidc_url=self.block.lti_1p3_oidc_url,
                lti_launch_url=self.block.lti_1p3_launch_url,
                client_id=self.lti_1p3_client_id,
                # Deployment ID hardcoded to 1 since
                # we're not using multi-tenancy.
                deployment_id="1",
                # XBlock Private RSA Key
                rsa_key=self.lti_1p3_private_key,
                rsa_key_id=self.lti_1p3_private_key_id,
                # LTI 1.3 Tool key/keyset url
                tool_key=self.block.lti_1p3_tool_public_key,
                tool_keyset_url=None,
            )

            # Check if enabled and setup LTI-AGS
            if self.block.has_score:

                default_values = {
                    'resource_id': self.block.location,
                    'score_maximum': self.block.weight,
                    'label': self.block.display_name,
                }

                if hasattr(self.block, 'start'):
                    default_values['start_date_time'] = self.block.start

                if hasattr(self.block, 'due'):
                    default_values['end_date_time'] = self.block.due

                # create LineItem if there is none for current lti configuration
                lineitem, _ = LtiAgsLineItem.objects.get_or_create(
                    lti_configuration=self,
                    resource_link_id=self.block.location,
                    defaults=default_values
                )

                consumer.enable_ags(
                    lineitems_url=get_lti_ags_lineitems_url(self.id),
                    lineitem_url=get_lti_ags_lineitems_url(self.id, lineitem.id),
                )

            return consumer

        # There's no configuration stored locally, so throw
        # NotImplemented.
        raise NotImplementedError

    def get_lti_consumer(self):
        """
        Returns an instanced class of LTI 1.1 or 1.3 consumer.
        """
        if self.version == self.LTI_1P3:
            return self._get_lti_1p3_consumer()

        return self._get_lti_1p1_consumer()

    def __str__(self):
        return "[{}] {} - {}".format(self.config_store, self.version, self.location)

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

    def save(self, *args, **kwargs):  # pylint: disable=arguments-differ
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
