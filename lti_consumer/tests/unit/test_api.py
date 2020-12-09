"""
Tests for LTI API.
"""
from unittest.mock import Mock, patch

from Cryptodome.PublicKey import RSA
from django.test.testcases import TestCase

from lti_consumer.api import (
    _get_or_create_local_lti_config,
    get_lti_1p3_launch_info,
    get_lti_1p3_launch_start_url,
    get_lti_consumer
)
from lti_consumer.lti_xblock import LtiConsumerXBlock
from lti_consumer.models import LtiConfiguration
from lti_consumer.tests.unit.test_utils import make_xblock


class TestGetOrCreateLocalLtiConfiguration(TestCase):
    """
    Unit tests for _get_or_create_local_lti_config API method.
    """
    def test_create_lti_config_if_inexistent(self):
        """
        Check if the API creates a model if no object matching properties is found.
        """
        location = 'block-v1:course+test+2020+type@problem+block@test'
        lti_version = LtiConfiguration.LTI_1P3

        # Check that there's nothing in the models
        self.assertEqual(LtiConfiguration.objects.all().count(), 0)

        # Call API
        lti_config = _get_or_create_local_lti_config(
            lti_version=lti_version,
            block_location=location
        )

        # Check if the object was created
        self.assertEqual(lti_config.version, lti_version)
        self.assertEqual(str(lti_config.location), location)
        self.assertEqual(lti_config.config_store, LtiConfiguration.CONFIG_ON_XBLOCK)

    def test_retrieve_existing(self):
        """
        Check if the API retrieves a model if the configuration matches.
        """
        location = 'block-v1:course+test+2020+type@problem+block@test'
        lti_version = LtiConfiguration.LTI_1P1

        lti_config = LtiConfiguration.objects.create(
            location=location
        )

        # Call API
        lti_config_retrieved = _get_or_create_local_lti_config(
            lti_version=lti_version,
            block_location=location
        )

        # Check if the object was created
        self.assertEqual(LtiConfiguration.objects.all().count(), 1)
        self.assertEqual(lti_config_retrieved, lti_config)

    def test_update_lti_version(self):
        """
        Check if the API retrieves the config and updates the API version.
        """
        location = 'block-v1:course+test+2020+type@problem+block@test'

        lti_config = LtiConfiguration.objects.create(
            location=location,
            version=LtiConfiguration.LTI_1P1
        )

        # Call API
        _get_or_create_local_lti_config(
            lti_version=LtiConfiguration.LTI_1P3,
            block_location=location
        )

        # Check if the object was created
        lti_config.refresh_from_db()
        self.assertEqual(lti_config.version, LtiConfiguration.LTI_1P3)


class TestGetLtiConsumer(TestCase):
    """
    Unit tests for get_lti_consumer API method.
    """
    def test_retrieve_with_block(self):
        """
        Check if the API creates a model if no object matching properties is found.
        """
        block = Mock()
        block.location = 'block-v1:course+test+2020+type@problem+block@test'
        block.lti_version = LtiConfiguration.LTI_1P3
        LtiConfiguration.objects.create(location=block.location)

        # Call API
        with patch("lti_consumer.models.LtiConfiguration.get_lti_consumer") as mock_get_lti_consumer:
            get_lti_consumer(block=block)
            mock_get_lti_consumer.assert_called_once()

        # Check that there's just a single LTI Config in the models
        self.assertEqual(LtiConfiguration.objects.all().count(), 1)

    def test_retrieve_with_id(self):
        """
        Check if the API retrieves a model if the configuration matches.
        """
        location = 'block-v1:course+test+2020+type@problem+block@test'
        lti_config = LtiConfiguration.objects.create(location=location)

        # Call API
        with patch("lti_consumer.models.LtiConfiguration.get_lti_consumer") as mock_get_lti_consumer:
            get_lti_consumer(config_id=lti_config.id)
            mock_get_lti_consumer.assert_called_once()


class TestGetLti1p3LaunchInfo(TestCase):
    """
    Unit tests for get_lti_consumer API method.
    """
    def setUp(self):
        # Patch internal method to avoid calls to modulestore
        patcher = patch(
            'lti_consumer.models.LtiConfiguration.get_lti_consumer',
        )
        self.addCleanup(patcher.stop)
        self._get_lti_consumer_patch = patcher.start()
        mock_consumer = Mock()
        mock_consumer.prepare_preflight_url.return_value = "http://example.com"
        self._get_lti_consumer_patch.return_value = mock_consumer

        return super().setUp()

    def test_no_parameters(self):
        """
        Check if the API creates a model if no object matching properties is found.
        """
        with self.assertRaises(Exception):
            get_lti_1p3_launch_info()

    def test_retrieve_with_id(self):
        """
        Check if the API retrieves the launch with id.
        """
        location = 'block-v1:course+test+2020+type@problem+block@test'
        lti_config = LtiConfiguration.objects.create(location=location)

        # Call and check returns
        launch_info = get_lti_1p3_launch_info(config_id=lti_config.id)

        # Not checking all data here, there's a test specific for that
        self.assertEqual(launch_info['client_id'], lti_config.lti_1p3_client_id)

    def test_retrieve_with_block(self):
        """
        Check if the API creates the model and retrieved correct info.
        """
        block = Mock()
        block.location = 'block-v1:course+test+2020+type@problem+block@test'
        block.lti_version = LtiConfiguration.LTI_1P3
        LtiConfiguration.objects.create(location=block.location)

        # Call API
        launch_info = get_lti_1p3_launch_info(block=block)

        # Retrieve created config and check full launch info data
        lti_config = LtiConfiguration.objects.get()
        self.assertCountEqual(
            launch_info,
            {
                'client_id': lti_config.lti_1p3_client_id,
                'keyset_url': 'https://example.com/api/lti_consumer/v1/public_keysets/{}'.format(
                    lti_config.lti_1p3_client_id
                ),
                'deployment_id': '1',
                'oidc_callback': 'https://example.com/api/lti_consumer/v1/launch/',
                'token_url': 'https://example.com/api/lti_consumer/v1/token/{}'.format(
                    lti_config.lti_1p3_client_id
                ),
                'deep_linking_launch_url': 'https://example.com'
            }
        )


class TestGetLti1p3LaunchUrl(TestCase):
    """
    Unit tests for get_lti_1p3_launch_start_url API method.
    """
    def test_no_parameters(self):
        """
        Check if the API creates a model if no object matching properties is found.
        """
        with self.assertRaises(Exception):
            get_lti_1p3_launch_start_url()

    def test_retrieve_url(self):
        """
        Check if the correct launch url is retrieved
        """
        # Generate RSA and save exports
        rsa_key = RSA.generate(1024)
        public_key = rsa_key.publickey().export_key()

        xblock_attributes = {
            'lti_version': 'lti_1p3',
            'lti_1p3_launch_url': 'http://tool.example/launch',
            'lti_1p3_oidc_url': 'http://tool.example/oidc',
            # We need to set the values below because they are not automatically
            # generated until the user selects `lti_version == 'lti_1p3'` on the
            # Studio configuration view.
            'lti_1p3_tool_public_key': public_key,
        }
        xblock = make_xblock('lti_consumer', LtiConsumerXBlock, xblock_attributes)
        # Set dummy location so that UsageKey lookup is valid
        xblock.location = 'block-v1:course+test+2020+type@problem+block@test'

        # Call API for normal LTI launch initiation
        launch_url = get_lti_1p3_launch_start_url(block=xblock, hint="test_hint")
        self.assertIn('login_hint=test_hint', launch_url)
        self.assertIn('lti_message_hint=', launch_url)

        # Call API for deep link launch
        launch_url = get_lti_1p3_launch_start_url(block=xblock, deep_link_launch=True)
        self.assertIn('lti_message_hint=deep_linking_launch', launch_url)
