"""
Tests for LTI 1.3 endpoint views.
"""
from mock import patch

from django.http import HttpResponse
from django.test.testcases import TestCase


class TestLti1p3KeysetEndpoint(TestCase):
    """
    Test `public_keyset_endpoint` method.
    """
    def setUp(self):
        super(TestLti1p3KeysetEndpoint, self).setUp()

        self.location = 'block-v1:course+test+2020+type@problem+block@test'
        self.url = '/lti_consumer/v1/public_keysets/{}'.format(self.location)

        # Patch settings calls to LMS method
        xblock_handler_patcher = patch(
            'lti_consumer.plugin.views.run_xblock_handler_noauth',
            return_value=HttpResponse()
        )
        self.addCleanup(xblock_handler_patcher.stop)
        self._mock_xblock_handler = xblock_handler_patcher.start()

    def test_public_keyset_endpoint(self):
        """
        Check that the keyset endpoint maps correctly to the
        `public_keyset_endpoint` XBlock handler endpoint.
        """
        response = self.client.get(self.url)

        # Check response
        self.assertEqual(response.status_code, 200)
        # Check function call arguments
        self._mock_xblock_handler.assert_called_once()
        kwargs = self._mock_xblock_handler.call_args.kwargs
        self.assertEqual(kwargs['usage_id'], self.location)
        self.assertEqual(kwargs['handler'], 'public_keyset_endpoint')

    def test_invalid_usage_key(self):
        """
        Check invalid methods yield HTTP code 404.
        """
        response = self.client.get('/lti_consumer/v1/public_keysets/invalid-key')
        self.assertEqual(response.status_code, 404)


class TestLti1p3LaunchGateEndpoint(TestCase):
    """
    Test `launch_gate_endpoint` method.
    """
    def setUp(self):
        super(TestLti1p3LaunchGateEndpoint, self).setUp()

        self.location = 'block-v1:course+test+2020+type@problem+block@test'
        self.url = '/lti_consumer/v1/launch/'
        self.request = {'login_hint': self.location}

        # Patch settings calls to LMS method
        xblock_handler_patcher = patch(
            'lti_consumer.plugin.views.run_xblock_handler',
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
        super(TestLti1p3AccessTokenEndpoint, self).setUp()

        self.location = 'block-v1:course+test+2020+type@problem+block@test'
        self.url = '/lti_consumer/v1/token/{}'.format(self.location)

        # Patch settings calls to LMS method
        xblock_handler_patcher = patch(
            'lti_consumer.plugin.views.run_xblock_handler_noauth',
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
