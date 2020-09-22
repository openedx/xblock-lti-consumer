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
        Check that the keyset endpoint works properly.
        """
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_invalid_usage_key(self):
        """
        Check invalid methods yield HTTP code 405.
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
        Check that the launch endpoint works properly.
        """
        response = self.client.get(self.url, self.request)
        self.assertEqual(response.status_code, 200)

    def test_invalid_usage_key(self):
        """
        Check invalid login_hint yields HTTP code 404.
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
        Check that the keyset endpoint works properly.
        """
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)

    def test_invalid_usage_key(self):
        """
        Check invalid methods yield HTTP code 404.
        """
        self._mock_xblock_handler.side_effect = Exception()
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 404)
