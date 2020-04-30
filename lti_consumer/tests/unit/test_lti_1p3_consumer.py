"""
Unit tests for LTI 1.3 consumer implementation
"""
from __future__ import absolute_import, unicode_literals

import json
import ddt

from mock import Mock, patch
from django.test.testcases import TestCase
from six.moves.urllib.parse import urlparse, parse_qs

from Crypto.PublicKey import RSA
from jwkest.jwk import load_jwks
from jwkest.jws import JWS

from lti_consumer.lti_1p3.consumer import LtiConsumer1p3


# Variables required for testing and verification
ISS = "http://test-platform.example/"
OIDC_URL = "http://test-platform/oidc"
LAUNCH_URL = "http://test-platform/launch"
CLIENT_ID = "1"
DEPLOYMENT_ID = "1"
# Consider storing a fixed key
RSA_KEY_ID = "1"
RSA_KEY = RSA.generate(2048).export_key('PEM')


# Test classes
@ddt.ddt
class TestLti1p3Consumer(TestCase):
    """
    Unit tests for LtiConsumer1p3
    """
    def setUp(self):
        super(TestLti1p3Consumer, self).setUp()

        # Set up consumer
        self.lti_consumer = LtiConsumer1p3(
            iss=ISS,
            lti_oidc_url=OIDC_URL,
            lti_launch_url=LAUNCH_URL,
            client_id=CLIENT_ID,
            deployment_id=DEPLOYMENT_ID,
            rsa_key=RSA_KEY,
            rsa_key_id=RSA_KEY_ID
        )

    def _setup_lti_user(self):
        """
        Set up a minimal LTI message with only required parameters.

        Currently, the only required parameters are the user data,
        but using a helper function to keep the usage consistent accross
        all tests.
        """
        self.lti_consumer.set_user_data(
            user_id="1",
            role="student",
        )

    def _get_lti_message(
            self,
            preflight_response=None,
            resource_link="link"
    ):
        """
        Retrieves a base LTI message with fixed test parameters.

        This function has valid default values, so it can be used to test custom
        parameters, but allows overriding them.
        """
        if preflight_response is None:
            preflight_response = {"nonce": "", "state": ""}

        return self.lti_consumer.generate_launch_request(
            preflight_response,
            resource_link
        )

    def _decode_token(self, token):
        """
        Checks for a valid signarute and decodes JWT signed LTI message

        This also tests the public keyset function.
        """
        public_keyset = self.lti_consumer.get_public_keyset()
        key_set = load_jwks(json.dumps(public_keyset))

        return JWS().verify_compact(token, keys=key_set)

    @ddt.data(
        (
            'student',
            ['http://purl.imsglobal.org/vocab/lis/v2/institution/person#Student']
        ),
        (
            'staff',
            [
                'http://purl.imsglobal.org/vocab/lis/v2/system/person#Administrator',
                'http://purl.imsglobal.org/vocab/lis/v2/institution/person#Instructor',
                'http://purl.imsglobal.org/vocab/lis/v2/institution/person#Student',
            ]
        )
    )
    @ddt.unpack
    def test_get_user_roles(self, role, expected_output):
        """
        Check that user roles are correctly translated to LTI 1.3 compliant rolenames.
        """
        roles = self.lti_consumer._get_user_roles(role)  # pylint: disable=protected-access
        self.assertItemsEqual(roles, expected_output)

    def test_get_user_roles_invalid(self):
        """
        Check that invalid user roles are throw a ValueError.
        """
        with self.assertRaises(ValueError):
            self.lti_consumer._get_user_roles('invalid')  # pylint: disable=protected-access

    def test_prepare_preflight_url(self):
        """
        Check if preflight request is properly formed and has all required keys.
        """
        preflight_request_data = self.lti_consumer.prepare_preflight_url(
            callback_url=LAUNCH_URL,
            hint="test-hint",
            lti_hint="test-lti-hint"
        )

        # Extract and check parameters from OIDC launch request url
        parameters = parse_qs(urlparse(preflight_request_data['oidc_url']).query)
        self.assertItemsEqual(
            parameters.keys(),
            [
                'iss',
                'login_hint',
                'lti_message_hint',
                'client_id',
                'target_link_uri',
                'lti_deployment_id'
            ]
        )
        self.assertEqual(parameters['iss'][0], ISS)
        self.assertEqual(parameters['client_id'][0], CLIENT_ID)
        self.assertEqual(parameters['login_hint'][0], "test-hint")
        self.assertEqual(parameters['lti_message_hint'][0], "test-lti-hint")
        self.assertEqual(parameters['lti_deployment_id'][0], DEPLOYMENT_ID)
        self.assertEqual(parameters['target_link_uri'][0], LAUNCH_URL)

    @ddt.data(
        # User with no roles
        (
            {"user_id": "1", "role": ''},
            {
                "sub": "1",
                "https://purl.imsglobal.org/spec/lti/claim/roles": []
            }
        ),
        # Student user, no optional data
        (
            {"user_id": "1", "role": 'student'},
            {
                "sub": "1",
                "https://purl.imsglobal.org/spec/lti/claim/roles": [
                    "http://purl.imsglobal.org/vocab/lis/v2/institution/person#Student"
                ]
            }
        ),
        # User with extra data
        (
            {"user_id": "1", "role": '', "full_name": "Jonh", "email_address": "jonh@example.com"},
            {
                "sub": "1",
                "https://purl.imsglobal.org/spec/lti/claim/roles": [],
                "name": "Jonh",
                "email": "jonh@example.com"
            }
        ),

    )
    @ddt.unpack
    def test_set_user_data(self, data, expected_output):
        """
        Check if setting user data works
        """
        self.lti_consumer.set_user_data(**data)
        self.assertEqual(
            self.lti_consumer.lti_claim_user_data,
            expected_output
        )

    @ddt.data(
        "iframe",
        "frame",
        "window"
    )
    def test_set_valid_presentation_claim(self, target):
        """
        Check if setting presentation claim data works
        """
        self._setup_lti_user()
        self.lti_consumer.set_launch_presentation_claim(document_target=target)
        self.assertEqual(
            self.lti_consumer.lti_claim_launch_presentation,
            {
                "https://purl.imsglobal.org/spec/lti/claim/launch_presentation": {
                    "document_target": target
                }
            }
        )

        # Prepare LTI message
        launch_request = self._get_lti_message()

        # Decode and verify message
        decoded = self._decode_token(launch_request['id_token'])
        self.assertIn(
            "https://purl.imsglobal.org/spec/lti/claim/launch_presentation",
            decoded.keys()
        )
        self.assertEqual(
            decoded["https://purl.imsglobal.org/spec/lti/claim/launch_presentation"],
            {
                "document_target": target
            }
        )

    def test_set_invalid_presentation_claim(self):
        """
        Check if setting invalid presentation claim data raises
        """
        with self.assertRaises(ValueError):
            self.lti_consumer.set_launch_presentation_claim(document_target="invalid")

    def test_check_no_user_data_error(self):
        """
        Check if the launch request fails if no user data is set.
        """
        with self.assertRaises(ValueError):
            self.lti_consumer.generate_launch_request(
                preflight_response=Mock(),
                resource_link=Mock()
            )

    @patch('time.time', return_value=1000)
    def test_launch_request(self, mock_time):
        """
        Check if the launch request works if user data is set.
        """
        self._setup_lti_user()
        launch_request = self._get_lti_message(
            preflight_response={
                "nonce": "test",
                "state": "state"
            },
            resource_link="link"
        )

        self.assertEqual(mock_time.call_count, 2)

        # Check launch request contents
        self.assertItemsEqual(launch_request.keys(), ['state', 'id_token'])
        self.assertEqual(launch_request['state'], 'state')
        # TODO: Decode and check token

    def test_custom_parameters(self):
        """
        Check if custom parameters are properly set.
        """
        custom_parameters = {
            "custom": "parameter",
        }

        self._setup_lti_user()
        self.lti_consumer.set_custom_parameters(custom_parameters)

        launch_request = self._get_lti_message()

        # Decode and verify message
        decoded = self._decode_token(launch_request['id_token'])
        self.assertIn(
            'https://purl.imsglobal.org/spec/lti/claim/custom',
            decoded.keys()
        )
        self.assertEqual(
            decoded["https://purl.imsglobal.org/spec/lti/claim/custom"],
            custom_parameters
        )

    def test_invalid_custom_parameters(self):
        """
        Check if invalid custom parameters raise exceptions.
        """
        with self.assertRaises(ValueError):
            self.lti_consumer.set_custom_parameters("invalid")
