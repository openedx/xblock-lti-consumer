"""
Unit tests for LTI 1.3 consumer implementation
"""
from __future__ import absolute_import, unicode_literals

import json
from urllib.parse import urlparse, parse_qs
import ddt

from mock import patch
from django.test.testcases import TestCase

from Cryptodome.PublicKey import RSA
from jwkest.jwk import load_jwks
from jwkest.jws import JWS

from lti_consumer.lti_1p3.constants import LTI_1P3_CONTEXT_TYPE
from lti_consumer.lti_1p3.consumer import LtiConsumer1p3, LtiAdvantageConsumer
from lti_consumer.lti_1p3.ags import LtiAgs
from lti_consumer.lti_1p3 import exceptions


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
            rsa_key_id=RSA_KEY_ID,
            # Use the same key for testing purposes
            tool_key=RSA_KEY
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
            preflight_response = {
                "client_id": CLIENT_ID,
                "redirect_uri": LAUNCH_URL,
                "nonce": NONCE,
                "state": STATE
            }

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
        ({"client_id": CLIENT_ID, "redirect_uri": LAUNCH_URL, "nonce": STATE, "state": STATE}, True),
        ({"client_id": "2", "redirect_uri": LAUNCH_URL, "nonce": STATE, "state": STATE}, False),
        ({"client_id": CLIENT_ID, "redirect_uri": LAUNCH_URL[::-1], "nonce": STATE, "state": STATE}, False),
        ({"redirect_uri": LAUNCH_URL, "nonce": NONCE, "state": STATE}, False),
        ({"client_id": CLIENT_ID, "nonce": NONCE, "state": STATE}, False),
        ({"client_id": CLIENT_ID, "redirect_uri": LAUNCH_URL, "state": STATE}, False),
        ({"client_id": CLIENT_ID, "redirect_uri": LAUNCH_URL, "nonce": NONCE}, False),
    )
    @ddt.unpack
    def test_preflight_validation(self, preflight_response, success):
        if success:
            return self.lti_consumer._validate_preflight_response(preflight_response)  # pylint: disable=protected-access
        with self.assertRaises(exceptions.PreflightRequestValidationFailure):
            return self.lti_consumer._validate_preflight_response(preflight_response)  # pylint: disable=protected-access

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
            ]
        )
    )
    @ddt.unpack
    def test_get_user_roles(self, role, expected_output):
        """
        Check that user roles are correctly translated to LTI 1.3 compliant rolenames.
        """
        roles = self.lti_consumer._get_user_roles(role)  # pylint: disable=protected-access
        self.assertCountEqual(roles, expected_output)

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
        parameters = parse_qs(urlparse(preflight_request_data).query)
        self.assertCountEqual(
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

    @ddt.data(
        *[context_type for context_type in LTI_1P3_CONTEXT_TYPE]  # pylint: disable=unnecessary-comprehension
    )
    def test_set_valid_context_claim(self, context_type):
        """
        Check if setting context claim data works
        """
        self._setup_lti_user()
        self.lti_consumer.set_context_claim(
            "context_id",
            context_types=[context_type],
            context_title="context_title",
            context_label="context_label"
        )

        expected_claim_data = {
            "id": "context_id",
            "type": [context_type.value],
            "title": "context_title",
            "label": "context_label",
        }

        self.assertEqual(
            self.lti_consumer.lti_claim_context,
            {
                "https://purl.imsglobal.org/spec/lti/claim/context": expected_claim_data
            }
        )

        # Prepare LTI message
        launch_request = self._get_lti_message()

        # Decode and verify message
        decoded = self._decode_token(launch_request['id_token'])
        self.assertIn(
            "https://purl.imsglobal.org/spec/lti/claim/context",
            decoded.keys()
        )
        self.assertEqual(
            decoded["https://purl.imsglobal.org/spec/lti/claim/context"],
            expected_claim_data
        )

    def test_set_invalid_context_claim_type(self):
        """
        Check if setting invalid context claim type omits type attribute
        """
        self._setup_lti_user()
        self.lti_consumer.set_context_claim(
            "context_id",
            context_types=["invalid"],
            context_title="context_title",
            context_label="context_label"
        )

        expected_claim_data = {
            "id": "context_id",
            "title": "context_title",
            "label": "context_label",
        }

        self.assertEqual(
            self.lti_consumer.lti_claim_context,
            {
                "https://purl.imsglobal.org/spec/lti/claim/context": expected_claim_data
            }
        )

        # Prepare LTI message
        launch_request = self._get_lti_message()

        # Decode and verify message
        decoded = self._decode_token(launch_request['id_token'])
        self.assertIn(
            "https://purl.imsglobal.org/spec/lti/claim/context",
            decoded.keys()
        )
        self.assertEqual(
            decoded["https://purl.imsglobal.org/spec/lti/claim/context"],
            expected_claim_data
        )

    def test_set_context_claim_with_only_id(self):
        """
        Check if setting no context claim type works
        """
        self._setup_lti_user()
        self.lti_consumer.set_context_claim(
            "context_id"
        )

        expected_claim_data = {
            "id": "context_id",
        }

        self.assertEqual(
            self.lti_consumer.lti_claim_context,
            {
                "https://purl.imsglobal.org/spec/lti/claim/context": expected_claim_data
            }
        )

        # Prepare LTI message
        launch_request = self._get_lti_message()

        # Decode and verify message
        decoded = self._decode_token(launch_request['id_token'])
        self.assertIn(
            "https://purl.imsglobal.org/spec/lti/claim/context",
            decoded.keys()
        )
        self.assertEqual(
            decoded["https://purl.imsglobal.org/spec/lti/claim/context"],
            expected_claim_data
        )

    def test_check_no_user_data_error(self):
        """
        Check if the launch request fails if no user data is set.
        """
        with self.assertRaises(ValueError):
            self._get_lti_message()

    @patch('time.time', return_value=1000)
    def test_launch_request(self, mock_time):
        """
        Check if the launch request works if user data is set.
        """
        self._setup_lti_user()
        launch_request = self._get_lti_message()

        self.assertEqual(mock_time.call_count, 2)

        # Check launch request contents
        self.assertCountEqual(launch_request.keys(), ['state', 'id_token'])
        self.assertEqual(launch_request['state'], STATE)
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

    def test_access_token_missing_params(self):
        """
        Check if access token with missing request data raises.
        """
        with self.assertRaises(exceptions.MissingRequiredClaim):
            self.lti_consumer.access_token({})

    def test_access_token_invalid_jwt(self):
        """
        Check if access token with invalid request data raises.
        """
        request_data = {
            "grant_type": "client_credentials",
            "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
            # This should be a valid JWT
            "client_assertion": "invalid-jwt",
            # Scope can be empty
            "scope": "",
        }

        with self.assertRaises(exceptions.MalformedJwtToken):
            self.lti_consumer.access_token(request_data)

    def test_access_token(self):
        """
        Check if a valid access token is returned.

        Since we're using the same key for both tool and
        platform here, we can make use of the internal
        _decode_token to check validity.
        """
        # Generate a dummy, but valid JWT
        token = self.lti_consumer.key_handler.encode_and_sign(
            {
                "test": "test"
            },
            expiration=1000
        )

        request_data = {
            # We don't actually care about these 2 first values
            "grant_type": "client_credentials",
            "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
            # This should be a valid JWT
            "client_assertion": token,
            # Scope can be empty
            "scope": "",
        }

        response = self.lti_consumer.access_token(request_data)

        # Check response contents
        self.assertIn('access_token', response)
        self.assertEqual(response.get('token_type'), 'bearer')
        self.assertEqual(response.get('expires_in'), 3600)
        self.assertEqual(response.get('scope'), '')

        # Check if token is valid
        self._decode_token(response.get('access_token'))

    def test_check_token_no_scopes(self):
        """
        Test if `check_token` method returns True for a valid token without scopes.
        """
        token = self.lti_consumer.key_handler.encode_and_sign({
            "iss": ISS,
            "scopes": "",
        })
        self.assertTrue(self.lti_consumer.check_token(token, None))

    def test_check_token_with_allowed_scopes(self):
        """
        Test if `check_token` method returns True for a valid token with allowed scopes.
        """
        token = self.lti_consumer.key_handler.encode_and_sign({
            "iss": ISS,
            "scopes": "test"
        })
        self.assertTrue(self.lti_consumer.check_token(token, ['test', '123']))

    def test_check_token_without_allowed_scopes(self):
        """
        Test if `check_token` method returns True for a valid token with allowed scopes.
        """
        token = self.lti_consumer.key_handler.encode_and_sign({
            "iss": ISS,
            "scopes": "test"
        })
        self.assertFalse(self.lti_consumer.check_token(token, ['123', ]))

    def test_extra_claim(self):
        """
        Check if extra claims are correctly added to the LTI message
        """
        self._setup_lti_user()
        self.lti_consumer.set_extra_claim({"fake_claim": "test"})

        # Retrieve launch message
        launch_request = self._get_lti_message()

        # Decode and verify message
        decoded = self._decode_token(launch_request['id_token'])
        self.assertIn(
            'fake_claim',
            decoded.keys()
        )
        self.assertEqual(
            decoded["fake_claim"],
            "test"
        )

    @ddt.data("invalid", None, 0)
    def test_extra_claim_invalid(self, test_value):
        """
        Check if extra claims thrown when passed anything other than dicts.
        """
        with self.assertRaises(ValueError):
            self.lti_consumer.set_extra_claim(test_value)


@ddt.ddt
class TestLtiAdvantageConsumer(TestCase):
    """
    Unit tests for LtiAdvantageConsumer
    """
    def setUp(self):
        super(TestLtiAdvantageConsumer, self).setUp()

        # Set up consumer
        self.lti_consumer = LtiAdvantageConsumer(
            iss=ISS,
            lti_oidc_url=OIDC_URL,
            lti_launch_url=LAUNCH_URL,
            client_id=CLIENT_ID,
            deployment_id=DEPLOYMENT_ID,
            rsa_key=RSA_KEY,
            rsa_key_id=RSA_KEY_ID,
            # Use the same key for testing purposes
            tool_key=RSA_KEY
        )

    def test_no_ags_returns_failure(self):
        """
        Test that when LTI-AGS isn't configured, the class yields an error.
        """
        with self.assertRaises(exceptions.LtiAdvantageServiceNotSetUp):
            self.lti_consumer.lti_ags  # pylint: disable=pointless-statement

    def test_enable_ags(self):
        """
        Test enabling LTI AGS and checking that required parameters are set.
        """
        self.lti_consumer.enable_ags("http://example.com/lineitems")

        # Check that the AGS class was properly instanced and set
        self.assertEqual(type(self.lti_consumer.ags), LtiAgs)

        # Check retrieving class works
        lti_ags_class = self.lti_consumer.lti_ags
        self.assertEqual(self.lti_consumer.ags, lti_ags_class)

        # Check that enabling the AGS adds the LTI AGS claim
        # in the launch message
        self.assertEqual(
            self.lti_consumer.extra_claims,
            {
                'https://purl.imsglobal.org/spec/lti-ags/claim/endpoint': {
                    'scope': [
                        'https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly',
                        'https://purl.imsglobal.org/spec/lti-ags/scope/result.readonly',
                        'https://purl.imsglobal.org/spec/lti-ags/scope/score',
                    ],
                    'lineitems': 'http://example.com/lineitems',
                }
            }
        )
