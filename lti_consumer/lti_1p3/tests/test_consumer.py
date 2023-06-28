"""
Unit tests for LTI 1.3 consumer implementation
"""

import json
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
import uuid

import ddt
from Cryptodome.PublicKey import RSA
from django.conf import settings
from django.test.testcases import TestCase
from edx_django_utils.cache import get_cache_key, TieredCache
from jwkest.jwk import load_jwks
from jwkest.jws import JWS

from lti_consumer.data import Lti1p3LaunchData
from lti_consumer.lti_1p3 import exceptions
from lti_consumer.lti_1p3.ags import LtiAgs
from lti_consumer.lti_1p3.deep_linking import LtiDeepLinking
from lti_consumer.lti_1p3.nprs import LtiNrps
from lti_consumer.lti_1p3.constants import LTI_1P3_CONTEXT_TYPE, LTI_PROCTORING_DATA_KEYS
from lti_consumer.lti_1p3.consumer import LtiAdvantageConsumer, LtiConsumer1p3, LtiProctoringConsumer
from lti_consumer.lti_1p3.exceptions import InvalidClaimValue, MissingRequiredClaim


# Variables required for testing and verification
ISS = "http://test-platform.example/"
OIDC_URL = "http://test-platform/oidc"
LAUNCH_URL = "http://test-platform/launch"
REDIRECT_URIS = [LAUNCH_URL]
CLIENT_ID = "1"
DEPLOYMENT_ID = "1"
NONCE = "1234"
STATE = "ABCD"
# Consider storing a fixed key
RSA_KEY_ID = "1"
RSA_KEY = RSA.generate(2048).export_key('PEM')


def _generate_token_request_data(token, scope):
    """
    Helper function to generate requests to the access_token endpoint
    """
    return {
        # We don't actually care about these 2 first values
        "grant_type": "client_credentials",
        "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
        "client_assertion": token,
        "scope": scope,
    }


# Test classes
@ddt.ddt
class TestLti1p3Consumer(TestCase):
    """
    Unit tests for LtiConsumer1p3
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
            redirect_uris=REDIRECT_URIS,
            # Use the same key for testing purposes
            tool_key=RSA_KEY
        )

    def _setup_lti_launch_data(self):
        """
        Set up a minimal LTI message with only required parameters.

        Currently, the only required parameters are the user data and resource_link_data.
        """
        self.lti_consumer.set_user_data(
            user_id="1",
            role="student",
        )

        self.lti_consumer.set_resource_link_claim("resource_link_id")

    def _get_lti_message(
            self,
            preflight_response=None,
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
        ({"client_id": CLIENT_ID, "redirect_uri": "http://other.url", "nonce": STATE, "state": STATE}, False),
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
        user_id = "1"
        resource_link_id = "resource_link_id"
        launch_data = Lti1p3LaunchData(
            user_id=user_id,
            user_role="student",
            config_id="1",
            resource_link_id=resource_link_id,
        )

        preflight_request_data = self.lti_consumer.prepare_preflight_url(launch_data)

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
        self.assertEqual(parameters['login_hint'][0], user_id)
        self.assertEqual(parameters['lti_deployment_id'][0], DEPLOYMENT_ID)
        self.assertEqual(parameters['target_link_uri'][0], LAUNCH_URL)

        launch_data_key = get_cache_key(
            app="lti",
            key="launch_data",
            user_id=user_id,
            resource_link_id=resource_link_id
        )
        self.assertEqual(parameters['lti_message_hint'][0], launch_data_key)

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
            {
                "user_id": "1",
                "role": '',
                "full_name":
                "Jonh",
                "email_address":
                "jonh@example.com",
                "preferred_username": "johnuser"},
            {
                "sub": "1",
                "https://purl.imsglobal.org/spec/lti/claim/roles": [],
                "name": "Jonh",
                "email": "jonh@example.com",
                "preferred_username": "johnuser",
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

    def test_check_no_user_data_error(self):
        """
        Check if the launch request fails if no user data is set.
        """
        with self.assertRaises(ValueError) as context_manager:
            self._get_lti_message()

        self.assertEqual(str(context_manager.exception), "Required user data isn't set.")

    @ddt.data(
        "iframe",
        "frame",
        "window"
    )
    def test_set_valid_presentation_claim(self, target):
        """
        Check if setting presentation claim data works
        """
        self._setup_lti_launch_data()

        return_url = "return_url"
        self.lti_consumer.set_launch_presentation_claim(
            document_target=target,
            return_url=return_url,
        )
        self.assertEqual(
            self.lti_consumer.lti_claim_launch_presentation,
            {
                "https://purl.imsglobal.org/spec/lti/claim/launch_presentation": {
                    "document_target": target,
                    "return_url": return_url,
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
                "document_target": target,
                "return_url": return_url,
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
        self._setup_lti_launch_data()
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
        self._setup_lti_launch_data()
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
        self._setup_lti_launch_data()
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

    @ddt.data(
        (
            {"resource_link_id": "id"},
            {
                "https://purl.imsglobal.org/spec/lti/claim/resource_link": {
                    "id": "id",
                }
            }
        ),
        (
            {"resource_link_id": "id", "description": "description", "title": "title"},
            {
                "https://purl.imsglobal.org/spec/lti/claim/resource_link": {
                    "id": "id",
                    "description": "description",
                    "title": "title",
                }
            }
        ),
    )
    @ddt.unpack
    def test_set_resource_link_claim(self, data, expected_output):
        """
        Test that setting the lti_consumer.lti_claim_resource_link attribute with
        the lti_consumer.set_resource_link_claim method works correctly.
        """
        self.lti_consumer.set_resource_link_claim(**data)
        self.assertEqual(
            self.lti_consumer.lti_claim_resource_link,
            expected_output
        )

    def test_check_no_resource_link_claim_error(self):
        """
        Check if the launch request fails if no resource_link data is set.
        """
        # In order to satisfy the user data check, set some user data.
        self.lti_consumer.set_user_data("1", "student")

        with self.assertRaises(ValueError) as context_manager:
            self._get_lti_message()

        self.assertEqual(str(context_manager.exception), "Required resource_link data isn't set.")

    @patch('time.time', return_value=1000)
    def test_launch_request(self, mock_time):
        """
        Check if the launch request works if user data is set.
        """
        self._setup_lti_launch_data()
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

        self._setup_lti_launch_data()
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

    def test_platform_instance_claim(self):
        """
        Check that the platform instance claim is present on launch
        """
        self._setup_lti_launch_data()
        launch_request = self._get_lti_message()

        # Decode and verify message
        decoded = self._decode_token(launch_request['id_token'])
        self.assertIn(
            "https://purl.imsglobal.org/spec/lti/claim/tool_platform",
            decoded.keys()
        )

        expected_data = {
            'guid': str(uuid.uuid5(uuid.NAMESPACE_DNS, settings.PLATFORM_NAME)),
            'name': settings.PLATFORM_NAME
        }
        self.assertEqual(
            decoded["https://purl.imsglobal.org/spec/lti/claim/tool_platform"],
            expected_data
        )

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
        request_data = _generate_token_request_data("invalid_jwt", "")

        with self.assertRaises(exceptions.MalformedJwtToken):
            self.lti_consumer.access_token(request_data)

    def test_access_token_no_acs(self):
        """
        Check that ACS does not work for the access token in the
        default LTI 1.3 consumer
        """
        # Generate a dummy, but valid JWT
        token = self.lti_consumer.key_handler.encode_and_sign(
            {
                "test": "test"
            },
            expiration=1000
        )

        request_data = _generate_token_request_data(token, "https://purl.imsglobal.org/spec/lti-ap/scope/control.all")

        response = self.lti_consumer.access_token(request_data)

        # Check no ACS scope present in returned token
        self.assertEqual(response.get('scope'), '')

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

        request_data = _generate_token_request_data(token, "")

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
        self._setup_lti_launch_data()
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
        super().setUp()

        # Set up consumer
        self.lti_consumer = LtiAdvantageConsumer(
            iss=ISS,
            lti_oidc_url=OIDC_URL,
            lti_launch_url=LAUNCH_URL,
            client_id=CLIENT_ID,
            deployment_id=DEPLOYMENT_ID,
            rsa_key=RSA_KEY,
            rsa_key_id=RSA_KEY_ID,
            redirect_uris=REDIRECT_URIS,
            # Use the same key for testing purposes
            tool_key=RSA_KEY
        )

        self.preflight_response = {}

    def _setup_lti_message_hint(self):
        """
        Instantiate Lti1p3LaunchData with the appropriate launch data and store it in the cache.

        Return the cache key that was used to store the Lti1p3LaunchData.
        """
        user_id = "1"
        resource_link_id = "resource_link_id"
        launch_data = Lti1p3LaunchData(
            user_id=user_id,
            user_role="student",
            config_id="1",
            resource_link_id=resource_link_id,
            message_type="LtiDeepLinkingRequest",
        )

        launch_data_key = get_cache_key(
            app="lti",
            key="launch_data",
            user_id=user_id,
            resource_link_id=resource_link_id,
        )
        TieredCache.set_all_tiers(launch_data_key, launch_data)

        return launch_data_key

    def _setup_deep_linking(self):
        """
        Set's up deep linking class in LTI consumer.
        """
        self.lti_consumer.enable_deep_linking("launch-url", "return-url")

        lti_message_hint = self._setup_lti_message_hint()

        # Set LTI Consumer parameters
        self.preflight_response = {
            "client_id": CLIENT_ID,
            "redirect_uri": LAUNCH_URL,
            "nonce": NONCE,
            "state": STATE,
            "lti_message_hint": lti_message_hint,
        }
        self.lti_consumer.set_user_data("1", "student")
        self.lti_consumer.set_resource_link_claim("resource_link_id")

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

    def test_enable_deep_linking(self):
        """
        Test enabling LTI Deep Linking.
        """
        self._setup_deep_linking()

        # Check that the Deep Linking class was properly instanced and set
        self.assertEqual(type(self.lti_consumer.dl), LtiDeepLinking)

        # Check retrieving class works
        lti_deep_linking_class = self.lti_consumer.lti_dl
        self.assertEqual(self.lti_consumer.dl, lti_deep_linking_class)

    def test_deep_linking_enabled_launch_request(self):
        """
        Test that the `generate_launch_request` returns a deep linking launch message
        when the preflight request indicates it.
        """
        self._setup_deep_linking()

        # Retrieve LTI Deep Link Launch Message
        token = self.lti_consumer.generate_launch_request(
            self.preflight_response,
        )['id_token']

        # Decode and check
        decoded_token = self.lti_consumer.key_handler.validate_and_decode(token)
        self.assertEqual(
            decoded_token['https://purl.imsglobal.org/spec/lti/claim/message_type'],
            "LtiDeepLinkingRequest",
        )
        self.assertEqual(
            decoded_token['https://purl.imsglobal.org/spec/lti-dl/claim/deep_linking_settings']['deep_link_return_url'],
            "return-url"
        )

    def test_deep_linking_token_decode_no_dl(self):
        """
        Check that trying to run the Deep Linking decoding fails if service is not set up.
        """
        with self.assertRaises(exceptions.LtiAdvantageServiceNotSetUp):
            self.lti_consumer.check_and_decode_deep_linking_token("token")

    def test_deep_linking_token_invalid_content_type(self):
        """
        Check that trying to run the Deep Linking decoding fails if an invalid content type is passed.
        """
        self._setup_deep_linking()

        # Dummy Deep linking response
        lti_reponse = {
            "https://purl.imsglobal.org/spec/lti/claim/message_type": "LtiDeepLinkingResponse",
            "https://purl.imsglobal.org/spec/lti-dl/claim/content_items": [
                {
                    "type": "wrongContentType",
                    "url": "https://something.example.com/page.html",
                },
            ]
        }

        with self.assertRaises(exceptions.LtiDeepLinkingContentTypeNotSupported):
            self.lti_consumer.check_and_decode_deep_linking_token(
                self.lti_consumer.key_handler.encode_and_sign(lti_reponse)
            )

    def test_deep_linking_token_wrong_message(self):
        """
        Check that trying to run the Deep Linking decoding fails if a message with the wrong type is passed.
        """
        self._setup_deep_linking()

        # Dummy Deep linking response
        lti_reponse = {"https://purl.imsglobal.org/spec/lti/claim/message_type": "WrongType"}

        with self.assertRaises(exceptions.InvalidClaimValue):
            self.lti_consumer.check_and_decode_deep_linking_token(
                self.lti_consumer.key_handler.encode_and_sign(lti_reponse)
            )

    def test_deep_linking_token_returned(self):
        """
        Check corect token decoding and retrieval of content_items.
        """
        self._setup_deep_linking()

        # Dummy Deep linking response
        lti_reponse = {
            "https://purl.imsglobal.org/spec/lti/claim/message_type": "LtiDeepLinkingResponse",
            "https://purl.imsglobal.org/spec/lti-dl/claim/content_items": []
        }

        content_items = self.lti_consumer.check_and_decode_deep_linking_token(
            self.lti_consumer.key_handler.encode_and_sign(lti_reponse)
        )

        self.assertEqual(content_items, [])

    def test_set_dl_content_launch_parameters(self):
        """
        Check that the DL overrides replace LTI launch parameters
        """
        self._setup_deep_linking()

        # Set DL variables and return LTI message
        self.lti_consumer.set_dl_content_launch_parameters(
            url="example.com",
            custom={"test": "test"},
        )
        message = self.lti_consumer.get_lti_launch_message("test_link")

        # Check if custom item was set
        self.assertEqual(
            message['https://purl.imsglobal.org/spec/lti/claim/custom'],
            {"test": "test"}
        )
        self.assertEqual(self.lti_consumer.launch_url, "example.com")

    def test_enable_nrps(self):
        """
        Test enabling LTI NRPS and checking that required parameters are set.
        """
        self.lti_consumer.enable_nrps("http://example.com/20/membership")

        # Check that the NRPS class was properly instanced and set
        self.assertIsInstance(self.lti_consumer.nrps, LtiNrps)

        # Check retrieving class works
        lti_nrps_class = self.lti_consumer.lti_nrps
        self.assertEqual(self.lti_consumer.nrps, lti_nrps_class)

        # Check that enabling the NRPS adds the LTI NRPS claim
        # in the launch message
        self.assertEqual(
            self.lti_consumer.extra_claims,
            {
                "https://purl.imsglobal.org/spec/lti-nrps/claim/namesroleservice": {
                    "context_memberships_url": "http://example.com/20/membership",
                    "service_versions": [
                        "2.0"
                    ]
                }
            }
        )


@ddt.ddt
class TestLtiProctoringConsumer(TestCase):
    """
    Unit tests for LtiProctoringConsumer
    """

    def setUp(self):
        super().setUp()

        # Set up consumer
        self.lti_consumer = LtiProctoringConsumer(
            iss=ISS,
            lti_oidc_url=OIDC_URL,
            lti_launch_url=LAUNCH_URL,
            client_id=CLIENT_ID,
            deployment_id=DEPLOYMENT_ID,
            rsa_key=RSA_KEY,
            rsa_key_id=RSA_KEY_ID,
            redirect_uris=REDIRECT_URIS,
            # Use the same key for testing purposes
            tool_key=RSA_KEY
        )

        self.preflight_response = {}

    def _setup_proctoring(self):
        """
        Sets up data necessary for a proctoring LTI launch.
        """
        # Set LTI Consumer parameters
        self.preflight_response = {
            "client_id": CLIENT_ID,
            "redirect_uri": LAUNCH_URL,
            "nonce": NONCE,
            "state": STATE,
            "lti_message_hint": "lti_message_hint",
        }
        self.lti_consumer.set_user_data("1", "student")
        self.lti_consumer.set_resource_link_claim("resource_link_id")

    def get_launch_data(self, **kwargs):
        """
        Returns a sample instance of Lti1p3LaunchData.
        """
        launch_data_kwargs = {
            "user_id": "user_id",
            "user_role": "student",
            "config_id": "1",
            "resource_link_id": "resource_link_id",
        }

        launch_data_kwargs.update(kwargs)

        return Lti1p3LaunchData(**launch_data_kwargs)

    @ddt.data(*LTI_PROCTORING_DATA_KEYS)
    def test_valid_set_proctoring_data(self, key):
        """
        Ensures that valid proctoring data can be set on an instance of LtiProctoringConsumer.
        """
        value = "test_value"
        self.lti_consumer.set_proctoring_data(**{key: value})

        actual_value = self.lti_consumer.proctoring_data[key]

        self.assertEqual(value, actual_value)

    def test_invalid_set_proctoring_data(self):
        """
        Ensures that an attempt to set invalid proctoring data on an instance of LtiProctoringConsumer does not update
        the consumer's proctoring_data.
        """
        self.lti_consumer.set_proctoring_data(test_key="test_value")

        self.assertEqual({}, self.lti_consumer.proctoring_data)

    def test_get_start_proctoring_claims(self):
        """
        Ensures that the correct claims are returned for a LtiStartProctoring LTI launch message.
        """
        self.lti_consumer.set_proctoring_data(
            attempt_number="attempt_number",
            session_data="session_data",
            start_assessment_url="start_assessment_url",
        )

        actual_start_proctoring_claims = self.lti_consumer.get_start_proctoring_claims()

        expected_start_proctoring_claims = {
            "https://purl.imsglobal.org/spec/lti-ap/claim/attempt_number": "attempt_number",
            "https://purl.imsglobal.org/spec/lti-ap/claim/session_data": "session_data",
            "https://purl.imsglobal.org/spec/lti/claim/message_type": "LtiStartProctoring",
            "https://purl.imsglobal.org/spec/lti-ap/claim/start_assessment_url": "start_assessment_url",
        }

        self.assertEqual(expected_start_proctoring_claims, actual_start_proctoring_claims)

    def test_get_end_assessment_claims(self):
        """
        Ensures that the correct claims are returned for a LtiEndAssessment LTI launch message.
        """
        self.lti_consumer.set_proctoring_data(
            attempt_number="attempt_number",
            session_data="session_data",
        )

        actual_get_end_assessment_claims = self.lti_consumer.get_end_assessment_claims()

        expected_get_end_assessment_claims = {
            "https://purl.imsglobal.org/spec/lti-ap/claim/attempt_number": "attempt_number",
            "https://purl.imsglobal.org/spec/lti-ap/claim/session_data": "session_data",
            "https://purl.imsglobal.org/spec/lti/claim/message_type": "LtiEndAssessment",
        }

        self.assertEqual(expected_get_end_assessment_claims, actual_get_end_assessment_claims)

    def test_assessment_control_claims(self):
        """
        Ensure the correct claims are returned for the assessment control service.
        """
        self.lti_consumer.set_proctoring_data(
            attempt_number="attempt_number",
            session_data="session_data",
            start_assessment_url="start_assessment_url",
            assessment_control_url="assessment_control_url",
            assessment_control_actions=["flagRequest", "terminateRequest"],
        )
        proctoring_acs_claims = self.lti_consumer.get_assessment_control_claim()

        expected_acs_claims = {
            "https://purl.imsglobal.org/spec/lti-ap/claim/acs": {
                "assessment_control_url": "assessment_control_url",
                "actions": ["flagRequest", "terminateRequest"],
            },
        }
        self.assertDictEqual(proctoring_acs_claims, expected_acs_claims)

    @ddt.data("LtiStartProctoring", "LtiEndAssessment")
    @patch('lti_consumer.lti_1p3.consumer.get_data_from_cache')
    def test_generate_launch_request(self, message_type, mock_get_data_from_cache):
        """
        Ensures that the correct claims are included in LTI launch messages for the LtiStartProctoring and
        LtiEndAssessment launch message types.
        """

        mock_launch_data = self.get_launch_data(message_type=message_type)
        mock_get_data_from_cache.return_value = mock_launch_data

        self._setup_proctoring()

        self.lti_consumer.set_proctoring_data(
            attempt_number="attempt_number",
            session_data="session_data",
            start_assessment_url="start_assessment_url",
        )

        token = self.lti_consumer.generate_launch_request(
            self.preflight_response,
        )['id_token']

        decoded_token = self.lti_consumer.key_handler.validate_and_decode(token)

        expected_claims = {}

        if message_type == "LtiStartProctoring":
            expected_claims = self.lti_consumer.get_start_proctoring_claims()
        else:
            expected_claims = self.lti_consumer.get_end_assessment_claims()

        decoded_token_claims = decoded_token.items()
        for claim in expected_claims.items():
            self.assertIn(claim, decoded_token_claims)

    @patch('lti_consumer.lti_1p3.consumer.get_data_from_cache')
    def test_generate_basic_launch_request(self, mock_get_data_from_cache):
        mock_launch_data = self.get_launch_data(message_type="LtiResourceLinkRequest")
        mock_get_data_from_cache.return_value = mock_launch_data

        self._setup_proctoring()
        token = self.lti_consumer.generate_launch_request(
            self.preflight_response,
        )['id_token']

        # just check token is valid
        self.lti_consumer.key_handler.validate_and_decode(token)

    @patch('lti_consumer.lti_1p3.consumer.get_data_from_cache')
    def test_enable_assessment_control(self, mock_get_data_from_cache):
        """
        Ensure that the correct claims are included in LTI launch messages with an ACS url set.
        """

        mock_launch_data = self.get_launch_data(message_type="LtiStartProctoring")
        mock_get_data_from_cache.return_value = mock_launch_data
        self._setup_proctoring()

        self.lti_consumer.set_proctoring_data(
            attempt_number="attempt_number",
            session_data="session_data",
            start_assessment_url="start_assessment_url",
            assessment_control_url="assessment_control_url",
            assessment_control_actions=["flagRequest", "terminateRequest"],
        )

        token = self.lti_consumer.generate_launch_request(
            self.preflight_response,
        )['id_token']

        decoded_token = self.lti_consumer.key_handler.validate_and_decode(token)
        expected_claims = self.lti_consumer.get_start_proctoring_claims()
        expected_claims.update(self.lti_consumer.get_assessment_control_claim())

        decoded_token_claims = decoded_token.items()
        for claim in expected_claims.items():
            self.assertIn(claim, decoded_token_claims)

    @patch('lti_consumer.lti_1p3.consumer.get_data_from_cache')
    def test_generate_launch_request_invalid_message(self, mock_get_data_from_cache):
        """
        Ensures that a ValueError is raised if the launch_data.message_type is not LtiStartProctoring,
        LtiEndAssessment, or LtiResourceLinkRequest.
        """

        mock_launch_data = self.get_launch_data(message_type="LtiDeepLinkingRequest")
        mock_get_data_from_cache.return_value = mock_launch_data

        self._setup_proctoring()

        self.lti_consumer.set_proctoring_data(
            attempt_number="attempt_number",
            session_data="session_data",
            start_assessment_url="start_assessment_url",
        )

        with self.assertRaises(ValueError):
            _ = self.lti_consumer.generate_launch_request(
                self.preflight_response,
            )['id_token']

    @ddt.data(
        "https://purl.imsglobal.org/spec/lti/claim/message_type",
        "https://purl.imsglobal.org/spec/lti/claim/version",
        "https://purl.imsglobal.org/spec/lti-ap/claim/session_data",
        "https://purl.imsglobal.org/spec/lti/claim/resource_link",
        "https://purl.imsglobal.org/spec/lti-ap/claim/attempt_number",
    )
    def test_invalid_check_and_decode_token(self, claim_key):
        """
        Ensures that LtiStartAssessment JWTs are correctly validated; ensures that missing or incorrect claims cause an
        InvalidClaimValue or MissingRequiredClaim exception to be raised.
        """
        self.lti_consumer.set_proctoring_data(
            attempt_number="attempt_number",
            session_data="session_data",
            start_assessment_url="start_assessment_url",
            resource_link_id="resource_link_id",
        )

        start_assessment_response = {
            "https://purl.imsglobal.org/spec/lti/claim/message_type": "LtiStartAssessment",
            "https://purl.imsglobal.org/spec/lti/claim/version": "1.3.0",
            "https://purl.imsglobal.org/spec/lti-ap/claim/session_data": "session_data",
            "https://purl.imsglobal.org/spec/lti/claim/resource_link": {"id": "resource_link_id"},
            "https://purl.imsglobal.org/spec/lti-ap/claim/attempt_number": "attempt_number",
        }

        # Check invalid claim values.
        start_assessment_response[claim_key] = {}
        encoded_token = self.lti_consumer.key_handler.encode_and_sign(
            message=start_assessment_response,
            expiration=3600
        )

        with self.assertRaises(InvalidClaimValue):
            self.lti_consumer.check_and_decode_token(encoded_token)

        # Check missing claims.
        del start_assessment_response[claim_key]
        encoded_token = self.lti_consumer.key_handler.encode_and_sign(
            message=start_assessment_response,
            expiration=3600
        )

        with self.assertRaises(MissingRequiredClaim):
            self.lti_consumer.check_and_decode_token(encoded_token)

    def test_access_token_no_valid_scopes(self):
        """
        Ensure that the no scopes are returned in the access token if the request scopes are invalid
        """
        # Generate a dummy, but valid JWT
        token = self.lti_consumer.key_handler.encode_and_sign(
            {
                "test": "test"
            },
            expiration=1000
        )

        # This should be a valid JWT w/ the ACS scope
        request_data = _generate_token_request_data(token, "invalid_scope")

        response = self.lti_consumer.access_token(request_data)

        # Check that the response has the ACS scope
        self.assertEqual(response.get('scope'), "")

    def test_access_token(self):
        """
        Ensure that the ACS scope is added based on the request to the access token endpoint
        """
        # Generate a dummy, but valid JWT
        token = self.lti_consumer.key_handler.encode_and_sign(
            {
                "test": "test"
            },
            expiration=1000
        )

        # This should be a valid JWT w/ the ACS scope
        request_data = _generate_token_request_data(token, "https://purl.imsglobal.org/spec/lti-ap/scope/control.all")

        response = self.lti_consumer.access_token(request_data)

        # Check that the response has the ACS scope
        self.assertEqual(response.get('scope'), "https://purl.imsglobal.org/spec/lti-ap/scope/control.all")

    def test_valid_check_and_decode_token(self):
        """
        Ensures that a valid LtiStartAssessment JWT is validated successfully.
        """
        self.lti_consumer.set_proctoring_data(
            attempt_number="attempt_number",
            session_data="session_data",
            start_assessment_url="start_assessment_url",
            resource_link_id="resource_link_id",
        )

        start_assessment_response = {
            "https://purl.imsglobal.org/spec/lti/claim/message_type": "LtiStartAssessment",
            "https://purl.imsglobal.org/spec/lti/claim/version": "1.3.0",
            "https://purl.imsglobal.org/spec/lti-ap/claim/session_data": "session_data",
            "https://purl.imsglobal.org/spec/lti/claim/resource_link": {"id": "resource_link_id"},
            "https://purl.imsglobal.org/spec/lti-ap/claim/attempt_number": "attempt_number",
            "https://purl.imsglobal.org/spec/lti-ap/claim/verified_user": {"name": "Bob"},
            "https://purl.imsglobal.org/spec/lti-ap/claim/end_assessment_return": "end_assessment_return",
        }

        encoded_token = self.lti_consumer.key_handler.encode_and_sign(
            message=start_assessment_response,
            expiration=3600
        )

        response = self.lti_consumer.check_and_decode_token(encoded_token)
        expected_response = {
            "end_assessment_return": "end_assessment_return",
            "verified_user": {"name": "Bob"},
            "resource_link": {"id": "resource_link_id"},
            "session_data": "session_data",
            "attempt_number": "attempt_number"
        }
        self.assertEqual(expected_response, response)
