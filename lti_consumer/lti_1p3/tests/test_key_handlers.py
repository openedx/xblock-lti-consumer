"""
Unit tests for LTI 1.3 consumer implementation
"""

import json
from unittest.mock import patch

import ddt
from Cryptodome.PublicKey import RSA
from django.test.testcases import TestCase
from jwkest import BadSignature
from jwkest.jwk import RSAKey, load_jwks
from jwkest.jws import JWS, NoSuitableSigningKeys, UnknownAlgorithm


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

    def test_encode_and_sign_no_suitable_keys(self):
        """
        Test if an exception is raised when there are no suitable keys when signing the JWT.
        """
        message = {
            "test": "test"
        }

        with patch('lti_consumer.lti_1p3.key_handlers.JWS.sign_compact', side_effect=NoSuitableSigningKeys):
            with self.assertRaises(exceptions.NoSuitableKeys):
                self.key_handler.encode_and_sign(message)

    def test_encode_and_sign_unknown_algorithm(self):
        """
        Test if an exception is raised when the signing algorithm is unknown when signing the JWT.
        """
        message = {
            "test": "test"
        }

        with patch('lti_consumer.lti_1p3.key_handlers.JWS.sign_compact', side_effect=UnknownAlgorithm):
            with self.assertRaises(exceptions.MalformedJwtToken):
                self.key_handler.encode_and_sign(message)

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

    # pylint: disable=unused-argument
    @patch('time.time', return_value=1000)
    def test_validate_and_decode(self, mock_time):
        """
        Test validate and decode with all parameters.
        """
        signed_token = self.key_handler.encode_and_sign(
            {
                "iss": "test-issuer",
                "aud": "test-aud",
            },
            expiration=1000
        )

        self.assertEqual(
            self.key_handler.validate_and_decode(signed_token),
            {
                "iss": "test-issuer",
                "aud": "test-aud",
                "iat": 1000,
                "exp": 2000
            }
        )

    # pylint: disable=unused-argument
    @patch('time.time', return_value=1000)
    def test_validate_and_decode_expired(self, mock_time):
        """
        Test validate and decode with all parameters.
        """
        signed_token = self.key_handler.encode_and_sign(
            {},
            expiration=-10
        )

        with self.assertRaises(exceptions.TokenSignatureExpired):
            self.key_handler.validate_and_decode(signed_token)

    def test_validate_and_decode_invalid_iss(self):
        """
        Test validate and decode with invalid iss.
        """
        signed_token = self.key_handler.encode_and_sign({"iss": "wrong"})

        with self.assertRaises(exceptions.InvalidClaimValue):
            self.key_handler.validate_and_decode(signed_token, iss="right")

    def test_validate_and_decode_invalid_aud(self):
        """
        Test validate and decode with invalid aud.
        """
        signed_token = self.key_handler.encode_and_sign({"aud": "wrong"})

        with self.assertRaises(exceptions.InvalidClaimValue):
            self.key_handler.validate_and_decode(signed_token, aud="right")

    def test_validate_and_decode_no_jwt(self):
        """
        Test validate and decode with invalid JWT.
        """
        with self.assertRaises(exceptions.MalformedJwtToken):
            self.key_handler.validate_and_decode("1.2.3")

    def test_validate_and_decode_no_keys(self):
        """
        Test validate and decode when no keys are available.
        """
        signed_token = self.key_handler.encode_and_sign({})
        # Changing the KID so it doesn't match
        self.key_handler.key.kid = "invalid_kid"

        with self.assertRaises(exceptions.NoSuitableKeys):
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

    @patch("lti_consumer.lti_1p3.key_handlers.JWS.verify_compact")
    def test_validate_and_decode_bad_signature(self, mock_verify_compact):
        mock_verify_compact.side_effect = BadSignature()

        key_handler = ToolKeyHandler()

        message = {
            "test": "test_message",
            "iat": 1000,
            "exp": 1200,
        }
        signed = create_jwt(self.key, message)

        # Decode and check results
        with self.assertRaises(exceptions.BadJwtSignature):
            key_handler.validate_and_decode(signed)
