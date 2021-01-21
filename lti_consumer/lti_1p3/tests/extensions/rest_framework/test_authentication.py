"""
Unit tests for LTI 1.3 consumer implementation
"""

from unittest.mock import MagicMock, patch

import ddt
from Cryptodome.PublicKey import RSA
from django.test.testcases import TestCase
from rest_framework import exceptions

from lti_consumer.lti_1p3.consumer import LtiConsumer1p3
from lti_consumer.lti_1p3.extensions.rest_framework.authentication import Lti1p3ApiAuthentication
from lti_consumer.models import LtiConfiguration

# Variables required for testing and verification
ISS = "http://test-platform.example/"
OIDC_URL = "http://test-platform/oidc"
LAUNCH_URL = "http://test-platform/launch"
CLIENT_ID = "1"
DEPLOYMENT_ID = "1"
NONCE = "1234"
STATE = "ABCD"
# Consider storing a fixed key
RSA_KEY_ID = "1"
RSA_KEY = RSA.generate(2048).export_key('PEM')


@ddt.ddt
class TestLtiAuthentication(TestCase):
    """
    Unit tests for Lti1p3ApiAuthentication class
    """
    def setUp(self):
        super().setUp()

        # Set up consumer
        self.lti_consumer = LtiConsumer1p3(
            iss=ISS,
            lti_oidc_url=OIDC_URL,
            lti_launch_url=LAUNCH_URL,
            client_id=CLIENT_ID,
            deployment_id=DEPLOYMENT_ID,
            rsa_key=RSA_KEY,
            rsa_key_id=RSA_KEY_ID,
            # Use the same key for testing purposes
            tool_key=RSA_KEY,
        )

        # Create LTI Configuration
        self.lti_configuration = LtiConfiguration.objects.create(
            version=LtiConfiguration.LTI_1P3,
        )

        # Patch call that retrieves config from modulestore
        # We're not testing the model here
        self._lti_block_patch = patch(
            'lti_consumer.models.LtiConfiguration.get_lti_consumer',
            return_value=self.lti_consumer,
        )
        self.addCleanup(self._lti_block_patch.stop)
        self._lti_block_patch.start()

    def _make_request(self):
        """
        Returns a Mock Request that can be used to test the LTI auth.
        """
        mock_request = MagicMock()

        # Generate a valid access token
        token = self.lti_consumer.key_handler.encode_and_sign(
            {
                "sub": self.lti_consumer.client_id,
                "iss": self.lti_consumer.iss,
                "scopes": "",
            },
            expiration=3600
        )
        mock_request.headers = {
            "Authorization": f"Bearer {token}",
        }

        # Set the lti config id in the "url"
        mock_request.parser_context = {"kwargs": {
            "lti_config_id": self.lti_configuration.id,
        }}

        return mock_request

    @ddt.data(
        None,
        "",
        "Bearer",
        "Bearer invalid token",
        # Valid token format, but cannot be decoded
        "Bearer invalid",
    )
    def test_invalid_auth_token(self, token):
        """
        Test invalid and auth token in auth mechanism.
        """
        mock_request = self._make_request()

        # Either set invalid token or clear headers
        if token is not None:
            mock_request.headers = {
                "Authorization": token,
            }
        else:
            mock_request.headers = {}

        with self.assertRaises(exceptions.AuthenticationFailed):
            auth = Lti1p3ApiAuthentication()
            auth.authenticate(mock_request)

    def test_no_lti_config(self):
        """
        Test that the login is invalid if LTI config doesn't exist.
        """
        mock_request = self._make_request()
        mock_request.parser_context = {"kwargs": {
            "lti_config_id": 0,  # Django id field is never zero
        }}

        with self.assertRaises(exceptions.AuthenticationFailed):
            auth = Lti1p3ApiAuthentication()
            auth.authenticate(mock_request)

    def test_lti_login_succeeds(self):
        """
        Test if login successful and that the LTI Consumer and token
        are attached to request.
        """
        mock_request = self._make_request()

        # Run auth
        auth = Lti1p3ApiAuthentication()
        auth.authenticate(mock_request)

        # Check request
        self.assertEqual(mock_request.lti_consumer, self.lti_consumer)
