"""
Tests for LTI 1.3 endpoint views.
"""
import json
from unittest.mock import patch, Mock

from django.http import HttpResponse
from django.test.testcases import TestCase

from Cryptodome.PublicKey import RSA
from jwkest.jwk import RSAKey, KEYS
from opaque_keys.edx.keys import UsageKey
from lti_consumer.models import LtiConfiguration
from lti_consumer.lti_1p3.exceptions import (
    MissingRequiredClaim,
    MalformedJwtToken,
    TokenSignatureExpired,
    NoSuitableKeys,
    UnknownClientId,
    UnsupportedGrantType
)
from lti_consumer.lti_1p3.tests.utils import create_jwt


class TestLti1p3KeysetEndpoint(TestCase):
    """
    Test `public_keyset_endpoint` method.
    """
    def setUp(self):
        super().setUp()

        self.location = 'block-v1:course+test+2020+type@problem+block@test'
        self.url = f'/lti_consumer/v1/public_keysets/{self.location}'

        # Set up LTI Configuration
        self.lti_config = LtiConfiguration.objects.create(
            version=LtiConfiguration.LTI_1P3,
            config_store=LtiConfiguration.CONFIG_ON_XBLOCK,
            location=UsageKey.from_string(self.location)
        )

    def test_public_keyset_endpoint(self):
        """
        Check that the keyset endpoint maps correctly to the
        `public_keyset_endpoint` XBlock handler endpoint.
        """
        response = self.client.get(self.url)

        # Check response
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-type'], 'application/json')
        self.assertEqual(response['Content-Disposition'], 'attachment; filename=keyset.json')

        # Check public keyset
        self.lti_config.refresh_from_db()
        self.assertEqual(
            self.lti_config.lti_1p3_public_jwk,
            json.loads(response.content.decode('utf-8'))
        )

    def test_invalid_usage_key(self):
        """
        Check invalid methods yield HTTP code 404.
        """
        response = self.client.get('/lti_consumer/v1/public_keysets/invalid-key')
        self.assertEqual(response.status_code, 404)

    def test_wrong_lti_version(self):
        """
        Check if trying to fetch the public keyset for LTI 1.1 yields a HTTP code 404.
        """
        self.lti_config.version = LtiConfiguration.LTI_1P1
        self.lti_config.save()

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)


class TestLti1p3LaunchGateEndpoint(TestCase):
    """
    Test `launch_gate_endpoint` method.
    """
    def setUp(self):
        super().setUp()

        self.location = 'block-v1:course+test+2020+type@problem+block@test'
        self.url = '/lti_consumer/v1/launch/'
        self.request = {'login_hint': self.location}

        # Patch settings calls to LMS method
        xblock_handler_patcher = patch(
            'lti_consumer.plugin.views.compat.run_xblock_handler',
            return_value=HttpResponse()
        )
        self.addCleanup(xblock_handler_patcher.stop)
        self._mock_xblock_handler = xblock_handler_patcher.start()

    def test_launch_gate(self):
        """
        Check that the launch endpoint correctly maps to the
        `lti_1p3_launch_callback` XBlock handler.
        """
        response = self.client.get(self.url, self.request)

        # Check response
        self.assertEqual(response.status_code, 200)
        # Check function call arguments
        self._mock_xblock_handler.assert_called_once()
        kwargs = self._mock_xblock_handler.call_args.kwargs
        self.assertEqual(kwargs['usage_id'], self.location)
        self.assertEqual(kwargs['handler'], 'lti_1p3_launch_callback')

    def test_invalid_usage_key(self):
        """
        Check that passing a invalid login_hint yields HTTP code 404.
        """
        self._mock_xblock_handler.side_effect = Exception()
        response = self.client.get(self.url, self.request)
        self.assertEqual(response.status_code, 404)


class TestLti1p3AccessTokenEndpoint(TestCase):
    """
    Test `access_token_endpoint` method.
    """
    def setUp(self):
        super().setUp()

        self.location = 'block-v1:course+test+2020+type@problem+block@test'
        self.url = f'/lti_consumer/v1/token/{self.location}'

        # Patch settings calls to LMS method
        self.mock_client = Mock()
        get_lti_consumer_patcher = patch(
            'lti_consumer.plugin.views.LtiConfiguration.get_lti_consumer',
            return_value=self.mock_client
        )
        self.addCleanup(get_lti_consumer_patcher.stop)
        self._mock_xblock_handler = get_lti_consumer_patcher.start()
        # Generate RSA
        self.key = RSAKey(key=RSA.generate(2048), kid="1")

    def get_body(self, token, **overrides):
        body = {
            "grant_type": "client_credentials",
            "client_assertion_type": "something",
            "client_assertion": token,
            "scope": "",
        }
        return {**body, **overrides}

    def test_access_token_endpoint(self):
        """
        Check that the access_token generated by the lti_consumer is returned.
        """
        token = {"access_token": "test-token"}
        self.mock_client.access_token.return_value = token

        config = LtiConfiguration(version=LtiConfiguration.LTI_1P3, location=self.location)
        config.save()

        body = self.get_body(create_jwt(self.key, {}))
        response = self.client.post(self.url, data=body)

        self.mock_client.access_token.called_once_with(body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), token)

    @patch('lti_consumer.plugin.views.UsageKey.from_string', side_effect=Exception())
    def test_invalid_usage_key(self, mock_usage_key):
        """
        Check invalid methods yield HTTP code 404.
        """
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 404)

    def test_non_existant_configuration_for_given_location(self):
        """
        Check that 404 is returned when there is no configuration for a given location
        """
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 404)

    def test_verify_lti_version_is_1p3(self):
        """
        Check that 400 is returned when the LTI version of the configuration is not 1.3
        """
        config = LtiConfiguration(version=LtiConfiguration.LTI_1P1, location=self.location)
        config.save()

        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'error': 'invalid_lti_version'})

        config.delete()

    def test_missing_required_claim(self):
        """
        Check that 400 is returned when required attributes are missing in the request
        """
        config = LtiConfiguration(version=LtiConfiguration.LTI_1P3, location=self.location)
        config.save()
        self.mock_client.access_token = Mock(side_effect=MissingRequiredClaim())

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'error': 'invalid_request'})

        config.delete()

    def test_token_errors(self):
        """
        Check invalid_grant error is returned when the token is invalid
        """
        config = LtiConfiguration(version=LtiConfiguration.LTI_1P3, location=self.location)
        config.save()

        self.mock_client.access_token = Mock(side_effect=MalformedJwtToken())
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'error': 'invalid_grant'})

        self.mock_client.access_token = Mock(side_effect=TokenSignatureExpired())
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'error': 'invalid_grant'})

        config.delete()

    def test_client_credential_errors(self):
        """
        Check invalid_client error is returned when the client credentials are wrong
        """
        config = LtiConfiguration(version=LtiConfiguration.LTI_1P3, location=self.location)
        config.save()

        self.mock_client.access_token = Mock(side_effect=NoSuitableKeys())
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'error': 'invalid_client'})

        self.mock_client.access_token = Mock(side_effect=UnknownClientId())
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'error': 'invalid_client'})

        config.delete()

    def test_unsupported_grant_error(self):
        """
        Check unsupported_grant_type is returned when the grant type is wrong
        """
        config = LtiConfiguration(version=LtiConfiguration.LTI_1P3, location=self.location)
        config.save()

        self.mock_client.access_token = Mock(side_effect=UnsupportedGrantType())
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'error': 'unsupported_grant_type'})

        config.delete()
