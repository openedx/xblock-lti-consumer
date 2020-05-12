"""
Unit tests for LTI 1.3 consumer implementation
"""
from __future__ import absolute_import, unicode_literals

import json
import ddt

from mock import patch
from django.test.testcases import TestCase

from Crypto.PublicKey import RSA
from jwkest.jwk import RSAKey, load_jwks
from jwkest.jws import JWS

from lti_consumer.lti_1p3.key_handlers import PlatformKeyHandler, ToolKeyHandler
from lti_consumer.lti_1p3 import exceptions
from .utils import create_jwt


@ddt.ddt
class TestPlatformKeyHandler(TestCase):
    """
    Unit tests for PlatformKeyHandler
    """
    def setUp(self):
        super(TestPlatformKeyHandler, self).setUp()

        self.rsa_key_id = "1"
        self.rsa_key = RSA.generate(2048).export_key('PEM')

        # Set up consumer
        self.key_handler = PlatformKeyHandler(
            key_pem=self.rsa_key,
            kid=self.rsa_key_id
        )

    def _decode_token(self, token):
        """
        Checks for a valid signarute and decodes JWT signed LTI message

        This also touches the public keyset method.
        """
        public_keyset = self.key_handler.get_public_jwk()
        key_set = load_jwks(json.dumps(public_keyset))

        return JWS().verify_compact(token, keys=key_set)

    def test_encode_and_sign(self):
        """
        Test if a message was correctly signed with RSA key.
        """
        message = {
            "test": "test"
        }
        signed_token = self.key_handler.encode_and_sign(message)
        self.assertEqual(
            self._decode_token(signed_token),
            message
        )

    # pylint: disable=unused-argument
    @patch('time.time', return_value=1000)
    def test_encode_and_sign_with_exp(self, mock_time):
        """
        Test if a message was correctly signed and has exp and iat parameters.
        """
        message = {
            "test": "test"
        }

        signed_token = self.key_handler.encode_and_sign(
            message,
            expiration=1000
        )

        self.assertEqual(
            self._decode_token(signed_token),
            {
                "test": "test",
                "iat": 1000,
                "exp": 2000
            }
        )

    def test_invalid_rsa_key(self):
        """
        Check that class raises when trying to import invalid RSA Key.
        """
        with self.assertRaises(exceptions.InvalidRsaKey):
            PlatformKeyHandler(key_pem="invalid PEM input")

    def test_empty_rsa_key(self):
        """
        Check that class doesn't fail instancing when not using a key.
        """
        empty_key_handler = PlatformKeyHandler(key_pem='')

        # Trying to encode a message should fail
        with self.assertRaises(exceptions.RsaKeyNotSet):
            empty_key_handler.encode_and_sign({})

        # Public JWK should return an empty value
        self.assertEqual(
            empty_key_handler.get_public_jwk(),
            {'keys': []}
        )


@ddt.ddt
class TestToolKeyHandler(TestCase):
    """
    Unit tests for ToolKeyHandler
    """
    def setUp(self):
        super(TestToolKeyHandler, self).setUp()

        self.rsa_key_id = "1"

        # Generate RSA and save exports
        rsa_key = RSA.generate(2048)
        self.key = RSAKey(
            key=rsa_key,
            kid=self.rsa_key_id
        )
        self.public_key = rsa_key.publickey().export_key()

        # Key handler
        self.key_handler = None

    def _setup_key_handler(self):
        """
        Set up a instance of the key handler.
        """
        self.key_handler = ToolKeyHandler(public_key=self.public_key)

    def test_import_rsa_key(self):
        """
        Check if the class is correctly instanced using a valid RSA key.
        """
        self._setup_key_handler()

    def test_import_invalid_rsa_key(self):
        """
        Check if the class errors out when using a invalid RSA key.
        """
        with self.assertRaises(exceptions.InvalidRsaKey):
            ToolKeyHandler(public_key="invalid-key")

    def test_get_empty_keyset(self):
        """
        Test getting an empty keyset.
        """
        key_handler = ToolKeyHandler()

        self.assertEqual(
            # pylint: disable=protected-access
            key_handler._get_keyset(),
            []
        )

    def test_get_keyset_with_pub_key(self):
        """
        Check that getting a keyset from a RSA key.
        """
        self._setup_key_handler()

        # pylint: disable=protected-access
        keyset = self.key_handler._get_keyset(kid=self.rsa_key_id)
        self.assertEqual(len(keyset), 1)
        self.assertEqual(
            keyset[0].kid,
            self.rsa_key_id
        )

    # pylint: disable=unused-argument
    @patch('time.time', return_value=1000)
    def test_validate_and_decode(self, mock_time):
        """
        Check that the validate and decode works.
        """
        self._setup_key_handler()

        message = {
            "test": "test_message",
            "iat": 1000,
            "exp": 1200,
        }
        signed = create_jwt(self.key, message)

        # Decode and check results
        decoded_message = self.key_handler.validate_and_decode(signed)
        self.assertEqual(decoded_message, message)

    # pylint: disable=unused-argument
    @patch('time.time', return_value=1000)
    def test_validate_and_decode_expired(self, mock_time):
        """
        Check that the validate and decode raises when signature expires.
        """
        self._setup_key_handler()

        message = {
            "test": "test_message",
            "iat": 900,
            "exp": 910,
        }
        signed = create_jwt(self.key, message)

        # Decode and check results
        with self.assertRaises(exceptions.TokenSignatureExpired):
            self.key_handler.validate_and_decode(signed)

    def test_validate_and_decode_no_keys(self):
        """
        Check that the validate and decode raises when no keys are found.
        """
        key_handler = ToolKeyHandler()

        message = {
            "test": "test_message",
            "iat": 900,
            "exp": 910,
        }
        signed = create_jwt(self.key, message)

        # Decode and check results
        with self.assertRaises(exceptions.NoSuitableKeys):
            key_handler.validate_and_decode(signed)
