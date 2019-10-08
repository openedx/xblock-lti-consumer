"""
Unit tests for lti_consumer.oauth module
"""

from __future__ import absolute_import

import unittest

from mock import Mock, patch

from lti_consumer.exceptions import LtiError
from lti_consumer.oauth import (get_oauth_request_signature,
                                log_authorization_header,
                                verify_oauth_body_signature)
from lti_consumer.tests.unit.test_utils import make_request

OAUTH_PARAMS = [
    (u'oauth_nonce', u'80966668944732164491378916897'),
    (u'oauth_timestamp', u'1378916897'),
    (u'oauth_version', u'1.0'),
    (u'oauth_signature_method', u'HMAC-SHA1'),
    (u'oauth_consumer_key', u'test'),
    (u'oauth_signature', u'frVp4JuvT1mVXlxktiAUjQ7%2F1cw%3D'),
]
OAUTH_PARAMS_WITH_BODY_HASH = OAUTH_PARAMS + [(u'oauth_body_hash', u'2jmj7l5rSw0yVb/vlWAYkK/YBwk=')]


class TestGetOauthRequestSignature(unittest.TestCase):
    """
    Unit tests for `lti_consumer.oauth.get_oauth_request_signature`
    """

    @patch('oauthlib.oauth1.Client.sign')
    def test_auth_header_returned(self, mock_client_sign):
        """
        Test that the correct Authorization header is returned
        """
        mock_client_sign.return_value = '', {'Authorization': ''}, ''
        signature = get_oauth_request_signature('test', 'secret', '', {}, '')

        mock_client_sign.assert_called_with('', http_method=u'POST', body='', headers={})
        self.assertEqual(signature, '')

    @patch('oauthlib.oauth1.Client.sign')
    def test_sign_raises_error(self, mock_client_sign):
        """
        Test that the correct Authorization header is returned
        """
        mock_client_sign.side_effect = ValueError

        with self.assertRaises(LtiError):
            __ = get_oauth_request_signature('test', 'secret', '', {}, '')


class TestVerifyOauthBodySignature(unittest.TestCase):
    """
    Unit tests for `lti_consumer.oauth.verify_oauth_body_signature`
    """

    @patch('oauthlib.oauth1.rfc5849.signature.verify_hmac_sha1', Mock(return_value=True))
    @patch('oauthlib.oauth1.rfc5849.signature.collect_parameters', Mock(return_value=OAUTH_PARAMS_WITH_BODY_HASH))
    def test_valid_signature(self):
        """
        Test True is returned when the request signature is valid
        """
        self.assertTrue(verify_oauth_body_signature(make_request(''), 'test', 'secret'))

    @patch('oauthlib.oauth1.rfc5849.signature.verify_hmac_sha1', Mock(return_value=False))
    @patch('oauthlib.oauth1.rfc5849.signature.collect_parameters', Mock(return_value=OAUTH_PARAMS_WITH_BODY_HASH))
    def test_invalid_signature(self):
        """
        Test exception is raised when the request signature is invalid
        """
        with self.assertRaises(LtiError):
            verify_oauth_body_signature(make_request(''), 'test', 'secret')

    @patch('oauthlib.oauth1.rfc5849.signature.verify_hmac_sha1', Mock(return_value=False))
    @patch('oauthlib.oauth1.rfc5849.signature.collect_parameters', Mock(return_value=OAUTH_PARAMS))
    def test_missing_oauth_body_hash(self):
        """
        Test exception is raised when the request signature is missing oauth_body_hash
        """
        with self.assertRaises(LtiError):
            verify_oauth_body_signature(make_request(''), 'test', 'secret')


class TestLogCorrectAuthorizationHeader(unittest.TestCase):
    """
    Unit tests for `lti_consumer.oauth.log_authorization_header`
    """

    @patch('lti_consumer.oauth.log')
    def test_log_auth_header(self, mock_log):
        """
        Test that log.debug is called
        """
        log_authorization_header(make_request(''), 'test', 'secret')
        self.assertTrue(mock_log.debug.called)
