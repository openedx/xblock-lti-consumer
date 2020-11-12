"""
Tests for LTI API.
"""
from django.test.testcases import TestCase
from mock import Mock, patch

from lti_consumer.api import (
    _get_or_create_local_lti_config,
    get_lti_consumer,
    get_lti_1p3_launch_info,
)
from lti_consumer.models import LtiConfiguration


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
            }
        )
