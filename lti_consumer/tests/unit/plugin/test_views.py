"""
Tests for LTI 1.3 endpoint views.
"""
import json
from unittest.mock import patch, Mock

import ddt

from django.test.testcases import TestCase
from django.urls import reverse

from Cryptodome.PublicKey import RSA
from jwkest.jwk import RSAKey
from opaque_keys.edx.keys import UsageKey
from lti_consumer.exceptions import LtiError
from lti_consumer.models import LtiConfiguration, LtiDlContentItem
from lti_consumer.lti_1p3.exceptions import (
    MissingRequiredClaim,
    MalformedJwtToken,
    TokenSignatureExpired,
    NoSuitableKeys,
    UnknownClientId,
    UnsupportedGrantType,
    PreflightRequestValidationFailure,
)
from lti_consumer.lti_xblock import LtiConsumerXBlock
from lti_consumer.lti_1p3.tests.utils import create_jwt
from lti_consumer.tests.unit.test_utils import make_xblock
from lti_consumer.plugin.views import parse_custom_parameters


class TestParseCustomParameters(TestCase):
    """
    Test `parse_custom_parameters` function.
    """

    @patch('lti_consumer.plugin.views.resolve_custom_parameter_template')
    def test_valid_custom_parameters(self, mock_resolve_custom_parameter_template):
        """
        Check works on valid custom parameters.
        """
        block = Mock()
        block.custom_parameters = ['test=test']

        result = parse_custom_parameters(block)

        mock_resolve_custom_parameter_template.assert_not_called()
        self.assertEqual(result, {'test': 'test'})

    @patch('lti_consumer.plugin.views.resolve_custom_parameter_template')
    def test_valid_dynamic_custom_parameters(self, mock_resolve_custom_parameter_template):
        """
        Check resolves dynamic custom parameters.
        """
        mock_resolve_custom_parameter_template.return_value = ''
        block = Mock()
        block.custom_parameters = ['test=${test}']

        result = parse_custom_parameters(block)

        mock_resolve_custom_parameter_template.assert_called_once()
        self.assertEqual(result, {'test': ''})

    def test_invalid_custom_parameters(self):
        """
        Check fails on invalid custom parameters.
        """
        block = Mock()
        block.custom_parameters = ['test']

        with self.assertRaises(LtiError):
            parse_custom_parameters(block)


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


@ddt.ddt
class TestLti1p3LaunchGateEndpoint(TestCase):
    """
    Tests for the `launch_gate_endpoint` method.
    """
    def setUp(self):
        super().setUp()

        self.location = 'block-v1:course+test+2020+type@problem+block@test'
        self.url = '/lti_consumer/v1/launch/'
        self.config = LtiConfiguration(
            version=LtiConfiguration.LTI_1P3,
            location=self.location,
            config_store=LtiConfiguration.CONFIG_ON_DB
        )
        self.config.save()

        self.xblock_attributes = {
            'lti_version': 'lti_1p3',
            'lti_1p3_launch_url': 'http://tool.example/launch',
            'lti_1p3_oidc_url': 'http://tool.example/oidc',
        }
        self.xblock = make_xblock('lti_consumer', LtiConsumerXBlock, self.xblock_attributes)
        # Set dummy location so that UsageKey lookup is valid
        self.xblock.location = self.location

        self.compat_patcher = patch("lti_consumer.plugin.views.compat")
        self.compat = self.compat_patcher.start()
        self.addCleanup(self.compat.stop)
        course = Mock(name="course")
        course.display_name_with_default = "course_display_name"
        course.display_org_with_default = "course_display_org"
        self.compat.get_course_by_id.return_value = course
        self.compat.get_user_role.return_value = "student"
        self.compat.get_external_id_for_user.return_value = "12345"
        model_compat_patcher = patch("lti_consumer.models.compat")
        model_compat = model_compat_patcher.start()
        model_compat.load_block_as_anonymous_user.return_value = self.xblock
        self.addCleanup(model_compat_patcher.stop)

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

    def test_lti_launch_response(self):
        """
        Check that the right launch response is generated
        """
        params = {
            "login_hint": self.location,
            "nonce": "nonce-value",
            "state": "hello-world",
            "redirect_uri": "https://tool.example",
            "client_id": self.config.lti_1p3_client_id
        }
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 200)

        content = response.content.decode('utf-8')
        self.assertIn("state", content)
        self.assertIn("hello-world", content)

    def test_launch_callback_endpoint_fails(self):
        """
        Test that the LTI 1.3 callback endpoint correctly display an error message.
        """
        # Make a fake invalid preflight request, with empty parameters
        response = self.client.get(self.url)

        # Check response and assert that state was inserted
        self.assertEqual(response.status_code, 400)

        response_body = response.content.decode('utf-8')
        self.assertIn("There was an error while launching the LTI tool.", response_body)
        self.assertNotIn("% trans", response_body)

        with patch(
            "lti_consumer.models.LtiAdvantageConsumer.generate_launch_request",
            side_effect=PreflightRequestValidationFailure()
        ):
            params = {
                "client_id": self.config.lti_1p3_client_id,
                "redirect_ur": "http://tool.example/launch",
                "state": "state_test_123",
                "nonce": "nonce",
                "login_hint": self.location
            }
            response = self.client.get(self.url, params)
            self.assertEqual(response.status_code, 400)

    def _setup_deep_linking(self, user_role='staff'):
        """
        Set up deep linking for data and mocking for testing.
        """
        self.config.config_store = LtiConfiguration.CONFIG_ON_XBLOCK
        self.config.save()

        self.compat.get_user_role.return_value = user_role
        mock_user_service = Mock()
        mock_user_service.get_external_user_id.return_value = 2
        self.xblock.runtime.service.return_value = mock_user_service

        self.xblock.course.display_name_with_default = 'course_display_name'
        self.xblock.course.display_org_with_default = 'course_display_org'

        # Enable deep linking
        self.xblock.lti_advantage_deep_linking_enabled = True

    def test_launch_callback_endpoint_deep_linking(self):
        """
        Test the LTI 1.3 callback endpoint for deep linking requests.
        """
        self._setup_deep_linking(user_role='staff')

        params = {
            "client_id": self.config.lti_1p3_client_id,
            "redirect_uri": "http://tool.example/launch",
            "state": "state_test_123",
            "nonce": "nonce",
            "login_hint": self.location,
            "lti_message_hint": "deep_linking_launch"
        }
        response = self.client.get(self.url, params)

        # Check response
        self.assertEqual(response.status_code, 200)

    @ddt.data(True, False)
    def test_launch_callback_endpoint_deep_linking_database_config(self, dl_enabled):
        """
        Test that Deep Linking is enabled and that the context is updated appropriately when using the 'database'
        config_type.
        """
        url = "http://tool.example/deep_linking_launch"
        self._setup_deep_linking(user_role='staff')

        self.xblock.config_type = 'database'

        LtiConfiguration.objects.filter(id=self.config.id).update(
            location=self.xblock.location,
            version=LtiConfiguration.LTI_1P3,
            config_store=LtiConfiguration.CONFIG_ON_DB,
            lti_advantage_deep_linking_enabled=dl_enabled,
            lti_advantage_deep_linking_launch_url=url,
        )
        if dl_enabled:
            self.xblock.lti_advantage_deep_linking_launch_url = url

        params = {
            "client_id": self.config.lti_1p3_client_id,
            "redirect_uri": "http://tool.example/launch",
            "state": "state_test_123",
            "nonce": "nonce",
            "login_hint": self.location,
            "lti_message_hint": "deep_linking_launch"
        }
        response = self.client.get(self.url, params)

        # Check response
        self.assertEqual(response.status_code, 200)
        response_body = response.content.decode('utf-8')

        # If Deep Linking is enabled, test that deep linking launch URL is in the rendered template. Otherwise, test
        # that it is not.
        if dl_enabled:
            self.assertIn(url, response_body)
        else:
            self.assertNotIn(url, response_body)

    def test_launch_callback_endpoint_deep_linking_by_student(self):
        """
        Test that the callback endpoint errors out if students try to do a deep link launch.
        """
        self._setup_deep_linking(user_role='student')
        # Enable deep linking
        self.xblock.lti_advantage_deep_linking_enabled = True

        params = {
            "client_id": self.config.lti_1p3_client_id,
            "redirect_uri": "http://tool.example/launch",
            "state": "state_test_123",
            "nonce": "nonce",
            "login_hint": self.location,
            "lti_message_hint": "deep_linking_launch"
        }
        response = self.client.get(self.url, params)

        # Check response
        self.assertEqual(response.status_code, 403)
        response_body = response.content.decode('utf-8')
        self.assertIn("Students don't have permissions to perform", response_body)
        self.assertNotIn("% trans", response_body)

    @patch('lti_consumer.plugin.views.LtiConfiguration.ltidlcontentitem_set')
    def test_callback_endpoint_dl_content_launch(self, mock_contentitem_set):
        """
        Test that the callback endpoint return the correct information when
        doing a `ltiResourceLink` deep linking launch.
        """
        self._setup_deep_linking(user_role='student')

        # Set deep linking mock data
        mock_contentitem_set.get.return_value.attributes = {
            "url": "https://deep-link-content/",
            "custom": {
                "parameter": "custom",
            },
        }

        params = {
            "client_id": self.config.lti_1p3_client_id,
            "redirect_uri": "http://tool.example/launch",
            "state": "state_test_123",
            "nonce": "nonce",
            "login_hint": self.location,
            "lti_message_hint": "deep_linking_content_launch:1"
        }
        response = self.client.get(self.url, params)
        content = response.content.decode('utf-8')

        # Check response
        self.assertEqual(response.status_code, 200)
        self.assertIn("http://tool.example/launch", content)

    @ddt.data(Mock(), None)
    @patch('lti_consumer.api.get_deep_linking_data')
    def test_callback_endpoint_dl_content_launch_database_config(self, dl_value, mock_lti_dl):
        self._setup_deep_linking(user_role="staff")
        self.xblock.config_type = 'database'
        mock_lti_dl.return_value = dl_value

        LtiConfiguration.objects.filter(id=self.config.id).update(
            lti_1p3_launch_url='http://tool.example/launch',
            lti_1p3_oidc_url='http://tool.example/oidc',
        )
        dl_item = LtiDlContentItem.objects.create(
            lti_configuration=self.config,
            content_type="link",
            attributes={"parameter": "custom"}
        )
        params = {
            "client_id": self.config.lti_1p3_client_id,
            "redirect_uri": "http://tool.example/launch",
            "state": "state_test_123",
            "nonce": "nonce",
            "login_hint": self.location,
            "lti_message_hint": f"deep_linking_content_launch:{dl_item.id}"
        }
        response = self.client.get(self.url, params)
        # Check response
        self.assertEqual(response.status_code, 200)

    @patch('lti_consumer.lti_1p3.consumer.LtiConsumer1p3.set_custom_parameters')
    @patch('lti_consumer.plugin.views.parse_custom_parameters')
    def test_launch_existing_custom_parameters(self, mock_set_custom_parameters, mock_parse_custom_parameters):
        """
        Check custom parameters are set if they exist on XBlock configuration.
        """
        mock_parse_custom_parameters.return_value = self.xblock
        self.xblock.custom_parameters = ['test=test']

        params = {
            "login_hint": self.location,
            "nonce": "nonce-value",
            "state": "hello-world",
            "redirect_uri": "https://tool.example",
            "client_id": self.config.lti_1p3_client_id
        }
        response = self.client.get(self.url, params)

        self.assertEqual(response.status_code, 200)
        mock_set_custom_parameters.assert_called_once_with(mock_parse_custom_parameters())

    @patch('lti_consumer.lti_1p3.consumer.LtiConsumer1p3.set_custom_parameters')
    def test_launch_non_existing_custom_parameters(self, mock_set_custom_parameters):
        """
        Check custom parameters are not set if they don't exist on XBlock configuration.
        """
        self.xblock.custom_parameters = []

        params = {
            "login_hint": self.location,
            "nonce": "nonce-value",
            "state": "hello-world",
            "redirect_uri": "https://tool.example",
            "client_id": self.config.lti_1p3_client_id
        }
        response = self.client.get(self.url, params)

        self.assertEqual(response.status_code, 200)
        mock_set_custom_parameters.assert_not_called()


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

    def test_access_token_endpoint_with_location_in_url(self):
        """
        Check that the access_token generated by the lti_consumer is returned.
        """
        token = {"access_token": "test-token"}
        self.mock_client.access_token.return_value = token

        url = reverse(
            'lti_consumer:lti_consumer.access_token_via_location',
            args=[str(self.config.location)]
        )
        body = self.get_body(create_jwt(self.key, {}))
        response = self.client.post(url, data=body)

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
