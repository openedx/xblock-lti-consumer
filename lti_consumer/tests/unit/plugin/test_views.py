"""
Tests for LTI 1.3 endpoint views.
"""
import json
from unittest.mock import patch, Mock

from django.http import HttpResponse
from django.test.testcases import TestCase
from django.urls import reverse

from Cryptodome.PublicKey import RSA
from jwkest.jwk import RSAKey
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
        Check that the keyset endpoint correctly returns the public jwk stored in db
        as a JSON file attachment.
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

    def test_public_keyset_endpoint_using_lti_config_id_in_url(self):
        """
        Check that the endpoint is accessible using the ID of the LTI Config object
        """
        response = self.client.get(f'/lti_consumer/v1/public_keysets/{self.lti_config.config_id}')

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


class TestLti1p3LaunchGateEndpoint(TestCase):
    """
    Test `launch_gate_endpoint` method.

    Majority of the functionality is tested in the test_lti_xblock.TestLtiConsumer1p3XBlock
    as the functionality was originally moved from there. It also acts as a verification
    for backward compatibility of the XBlock functionality.
    """
    def setUp(self):
        super().setUp()

        self.location = 'block-v1:course+test+2020+type@problem+block@test'
        self.url = '/lti_consumer/v1/launch/'
        self.config = LtiConfiguration(version=LtiConfiguration.LTI_1P3, location=self.location)
        self.config.save()

    def test_invalid_usage_key(self):
        """
        Check that passing a invalid login_hint yields HTTP code 404.
        """
        response = self.client.get(self.url, {"login_hint": "useless-location"})
        self.assertEqual(response.status_code, 404)

    def test_invalid_lti_version(self):
        """
        Check that a LTI 1.1 tool accessing this endpoint is returned a 404.
        """
        self.config.version = LtiConfiguration.LTI_1P1
        self.config.save()

        response = self.client.get(self.url, {"login_hint": self.location})
        self.assertEqual(response.status_code, 404)

        # Rollback
        self.config.version = LtiConfiguration.LTI_1P3
        self.config.save()

    def test_non_existant_lti_config(self):
        """
        Check that a 404 is returned when LtiConfiguration for a location doesn't exist
        """
        response = self.client.get(self.url, {"login_hint": self.location + "extra"})
        self.assertEqual(response.status_code, 404)


class TestLti1p3AccessTokenEndpoint(TestCase):
    """
    Test `access_token_endpoint` method.
    """
    def setUp(self):
        super().setUp()

        location = 'block-v1:course+test+2020+type@problem+block@test'
        self.config = LtiConfiguration(version=LtiConfiguration.LTI_1P3, location=location)
        self.config.save()
        self.url = reverse('lti_consumer:lti_consumer.access_token', args=[str(self.config.config_id)])
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
        """
        Create the JSON to form the request body using the token
        """
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

        body = self.get_body(create_jwt(self.key, {}))
        response = self.client.post(self.url, data=body)

        self.mock_client.access_token.called_once_with(body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), token)

    def test_non_existant_configuration_for_given_id(self):
        """
        Check that 404 is returned when there is no configuration for a given id
        """
        url = reverse('lti_consumer:lti_consumer.access_token', args=['075194d3-6885-417e-a8a8-6c931e272f00'])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)

    def test_verify_lti_version_is_1p3(self):
        """
        Check that 400 is returned when the LTI version of the configuration is not 1.3
        """
        self.config.version = LtiConfiguration.LTI_1P1
        self.config.save()

        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {'error': 'invalid_lti_version'})

        # Reset to 1P3 so other tests aren't affected.
        self.config.version = LtiConfiguration.LTI_1P3
        self.config.save()

    def test_missing_required_claim(self):
        """
        Check that 400 is returned when required attributes are missing in the request
        """
        self.mock_client.access_token = Mock(side_effect=MissingRequiredClaim())
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'error': 'invalid_request'})

    def test_token_errors(self):
        """
        Check invalid_grant error is returned when the token is invalid
        """
        self.mock_client.access_token = Mock(side_effect=MalformedJwtToken())
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'error': 'invalid_grant'})

        self.mock_client.access_token = Mock(side_effect=TokenSignatureExpired())
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'error': 'invalid_grant'})

    def test_client_credential_errors(self):
        """
        Check invalid_client error is returned when the client credentials are wrong
        """
        self.mock_client.access_token = Mock(side_effect=NoSuitableKeys())
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'error': 'invalid_client'})

        self.mock_client.access_token = Mock(side_effect=UnknownClientId())
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'error': 'invalid_client'})

    def test_unsupported_grant_error(self):
        """
        Check unsupported_grant_type is returned when the grant type is wrong
        """
        self.mock_client.access_token = Mock(side_effect=UnsupportedGrantType())
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'error': 'unsupported_grant_type'})


class TestLti1p3AccessTokenEndpointWithLocation(TestCase):
    """
    Test `access_token_endpoint_with_location` method.
    """
    def setUp(self):
        super().setUp()

        self.location = 'block-v1:course+test+2020+type@problem+block@test'
        self.url = f'/lti_consumer/v1/token/{self.location}'

        # Patch settings calls to LMS method
        xblock_handler_patcher = patch(
            'lti_consumer.plugin.views.compat.run_xblock_handler_noauth',
            return_value=HttpResponse()
        )
        self.addCleanup(xblock_handler_patcher.stop)
        self._mock_xblock_handler = xblock_handler_patcher.start()

    def test_access_token_endpoint(self):
        """
        Check that the keyset endpoint is correctly mapping to the
        `lti_1p3_access_token` XBlock handler.
        """
        response = self.client.post(self.url)

        # Check response
        self.assertEqual(response.status_code, 200)
        # Check function call arguments
        self._mock_xblock_handler.assert_called_once()
        kwargs = self._mock_xblock_handler.call_args.kwargs
        self.assertEqual(kwargs['usage_id'], self.location)
        self.assertEqual(kwargs['handler'], 'lti_1p3_access_token')

    def test_invalid_usage_key(self):
        """
        Check invalid methods yield HTTP code 404.
        """
        self._mock_xblock_handler.side_effect = Exception()
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 404)
