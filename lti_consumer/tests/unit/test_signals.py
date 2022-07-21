"""
Tests for the signals module
"""
from unittest.mock import patch
from django.test.testcases import TestCase

from lti_consumer.models import LtiConfiguration
from lti_consumer.lti_xblock import LtiConsumerXBlock
from .test_utils import make_xblock


class UpdateXBlockLtiConfigurationTestCase(TestCase):
    """
    Test case for the update_xblock_lti_configuration signal
    """
    def setUp(self):
        super().setUp()

        self.xblock = make_xblock('SignalsTestBlock', LtiConsumerXBlock, {})
        self.xblock.location = 'block-v1:course+test+2020+type@problem+block@test'

        # Patch compat
        compat_patcher = patch('lti_consumer.models.compat', **{
            'load_block_as_anonymous_user.return_value': self.xblock
        })
        self.addCleanup(compat_patcher.stop)
        compat_patcher.start()

    def test_xblock_is_updated_only_when_lti_config_is_changed(self):
        """
        The signal should update the XBlock only when specified LTI 1.3
        values are changed in the LtiConfiguration Model
        """
        config = LtiConfiguration(
            version=LtiConfiguration.LTI_1P3,
            location=self.xblock.location,
            config_store=LtiConfiguration.CONFIG_ON_DB,
        )
        config.save()

        config.lti_1p3_launch_url = "http://lti-1p3.launch.url"
        config.save()

        self.assertEqual(self.xblock.lti_1p3_launch_url, "http://lti-1p3.launch.url")

    def test_instance_where_the_block_is_not_present_are_handled_gracefully(self):
        """
        When the LtiConfiguration Model cannot load a Block, the signal should exit
        gracefully
        """
        config = LtiConfiguration.objects.create()

        config.lti_1p3_launch_url = "https://lti-1p3.launch.url"
        config.save()
        # Nothing to assert. This will fail when an unhandled exception is raised.
