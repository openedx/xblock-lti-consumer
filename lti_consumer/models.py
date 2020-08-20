"""
LTI configuration and linking models.
"""
from django.db import models

from opaque_keys.edx.django.models import UsageKeyField

# LTI 1.1
from lti_consumer.lti_1p1.consumer import LtiConsumer1p1
# LTI 1.3
from lti_consumer.lti_1p3.consumer import LtiConsumer1p3
from lti_consumer.utils import get_lms_base


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

            # Import on runtime only
            # pylint: disable=import-outside-toplevel,import-error
            from xmodule.modulestore.django import modulestore
            block = self._block = modulestore().get_item(self.location)
        return block

    @block.setter
    def block(self, block):
        """
        Allows preloading the block instead of fetching it from the modulestore.
        """
        self._block = block

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
            consumer = LtiConsumer1p3(
                iss=get_lms_base(),
                lti_oidc_url=self.block.lti_1p3_oidc_url,
                lti_launch_url=self.block.lti_1p3_launch_url,
                client_id=self.block.lti_1p3_client_id,
                # Deployment ID hardcoded to 1 since
                # we're not using multi-tenancy.
                deployment_id="1",
                # XBlock Private RSA Key
                rsa_key=self.block.lti_1p3_block_key,
                rsa_key_id=self.block.lti_1p3_client_id,
                # LTI 1.3 Tool key/keyset url
                tool_key=self.block.lti_1p3_tool_public_key,
                tool_keyset_url=None,
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
