"""
Unit tests for LTI 1.3 consumer implementation
"""

import json
import math
import time
from datetime import datetime, timezone
from unittest.mock import patch

import ddt
import jwt
from Cryptodome.PublicKey import RSA
from django.test.testcases import TestCase
from jwt.api_jwk import PyJWK

from lti_consumer.lti_1p3 import exceptions
from lti_consumer.lti_1p3.key_handlers import PlatformKeyHandler, ToolKeyHandler

from .utils import create_jwt


@ddt.ddt
class TestPlatformKeyHandler(TestCase):
    """
    Unit tests for PlatformKeyHandler
    """
    def setUp(self):
        super().setUp()

        self.rsa_key_id = "1"
        self.rsa_key = RSA.generate(2048).export_key('PEM')

        # Set up consumer
        self.key_handler = PlatformKeyHandler(
            key_pem=self.rsa_key,
            kid=self.rsa_key_id
        )

    def _decode_token(self, token, exp=True):
        """
        Checks for a valid signature and decodes JWT signed LTI message

        This also touches the public keyset method.
        """
        return self.key_handler.validate_and_decode(token, exp=exp)

    def test_encode_and_sign(self):
        """
        Test if a message was correctly signed with RSA key.
        """
        message = {
            "test": "test"
        }
        signed_token = self.key_handler.encode_and_sign(message)
        self.assertEqual(
            self._decode_token(signed_token, exp=False),
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
        expiration = int(datetime.now(tz=timezone.utc).timestamp())
        signed_token = self.key_handler.encode_and_sign(
            message,
            expiration=expiration
        )

        self.assertEqual(
            self._decode_token(signed_token),
            {
                "test": "test",
                "iat": 1000,
                "exp": expiration + 1000
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

    def test_validate_and_decode(self):
        """
        Test validate and decode with all parameters.
        """
        expiration = 1000
        signed_token = self.key_handler.encode_and_sign(
            {
                "iss": "test-issuer",
                "aud": "test-aud",
            },
            expiration=expiration
        )

        self.assertEqual(
            self.key_handler.validate_and_decode(signed_token),
            {
                "iss": "test-issuer",
                "aud": "test-aud",
                "iat": int(math.floor(time.time())),
                "exp": int(math.floor(time.time()) + expiration),
            }
        )

    def test_validate_and_decode_expired(self):
        """
        Test validate and decode with all parameters.
        """
        signed_token = self.key_handler.encode_and_sign(
            {},
            expiration=-10
        )

        with self.assertRaises(jwt.InvalidTokenError):
            self.key_handler.validate_and_decode(signed_token)

    def test_validate_and_decode_invalid_iss(self):
        """
        Test validate and decode with invalid iss.
        """
        signed_token = self.key_handler.encode_and_sign({"iss": "wrong"})

        with self.assertRaises(jwt.InvalidTokenError):
            self.key_handler.validate_and_decode(signed_token, iss="right")

    def test_validate_and_decode_invalid_aud(self):
        """
        Test validate and decode with invalid aud.
        """
        signed_token = self.key_handler.encode_and_sign({"aud": "wrong"})

        with self.assertRaises(jwt.InvalidTokenError):
            self.key_handler.validate_and_decode(signed_token, aud="right")

    def test_validate_and_decode_no_jwt(self):
        """
        Test validate and decode with invalid JWT.
        """
        with self.assertRaises(jwt.InvalidTokenError):
            self.key_handler.validate_and_decode("1.2.3")

    def test_validate_and_decode_no_keys(self):
        """
        Test validate and decode when no keys are available.
        """
        signed_token = self.key_handler.encode_and_sign({})

        self.key_handler.key = None

        with self.assertRaises(exceptions.RsaKeyNotSet):
            self.key_handler.validate_and_decode(signed_token)


@ddt.ddt
class TestToolKeyHandler(TestCase):
    """
    Unit tests for ToolKeyHandler
    """
    def setUp(self):
        super().setUp()

        self.rsa_key_id = "1"

        # Generate RSA and save exports
        rsa_key = RSA.generate(2048)
        algo_obj = jwt.get_algorithm_by_name('RS256')
        private_key = algo_obj.prepare_key(rsa_key.export_key())
        private_jwk = json.loads(algo_obj.to_jwk(private_key))
        private_jwk['kid'] = self.rsa_key_id
        self.key = PyJWK.from_dict(private_jwk)

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

    def test_validate_and_decode(self):
        """
        Check that the validate and decode works.
        """
        self._setup_key_handler()

        message = {
            "test": "test_message",
            "iat": 1000,
            "exp": int(math.floor(time.time()) + 1000),
        }
        signed = create_jwt(self.key, message)

        # Decode and check results
        decoded_message = self.key_handler.validate_and_decode(signed)
        self.assertEqual(decoded_message, message)

    def test_validate_and_decode_expired(self):
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
        with self.assertRaises(jwt.InvalidTokenError):
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
