"""
LTI 1.3 - Access token library

This handles validating messages sent by the tool and generating
access token with LTI scopes.
"""
import copy
import json
import math
import sys
import time
import logging

import jwt
from edx_django_utils.monitoring import function_trace
from jwt.api_jwk import PyJWK

from . import exceptions

log = logging.getLogger(__name__)


class ToolKeyHandler:
    """
    LTI 1.3 Tool Jwt Handler.

    Uses a tool public keys or keysets URL to retrieve
    a key and validate a message sent by the tool.

    This is primarily used by the Access Token endpoint
    in order to validate the JWT Signature of messages
    signed with the tools signature.
    """
    @function_trace('lti_consumer.key_handlers.ToolKeyHandler.__init__')
    def __init__(self, public_key=None, keyset_url=None):
        """
        Instance message validator

        Import a public key from the tool by either using a keyset url
        or a combination of public key + key id.

        Keyset URL takes precedence because it makes key rotation easier to do.
        """
        # Only store keyset URL to avoid blocking the class
        # instancing on an external url, which is only used
        # when validating a token.
        self.keyset_url = keyset_url
        self.public_key = None

        # Import from public key
        if public_key:
            try:
                # Import Key and save to internal state
                algo_obj = jwt.get_algorithm_by_name('RS256')
                public_key = algo_obj.prepare_key(public_key)
                public_jwk = json.loads(algo_obj.to_jwk(public_key))
                self.public_key = PyJWK.from_dict(public_jwk)
            except jwt.exceptions.InvalidKeyError as err:
                log.warning(
                    'An error was encountered while loading the LTI tool\'s key from the public key. '
                    'The RSA key could not parsed.'
                )
                raise exceptions.InvalidRsaKey() from err

    def _get_keyset(self):
        """
        Get keyset from available sources.

        If using a RSA key, forcefully set the key id
        to match the one from the JWT token.
        """
        keyset = []

        if self.keyset_url:
            try:
                keys = jwt.PyJWKClient(self.keyset_url).get_jwk_set()
            except Exception as err:
                # Broad Exception is required here because jwkest raises
                # an Exception object explicitly.
                # Beware that many different scenarios are being handled
                # as an invalid key when the JWK loading fails.
                log.warning(
                    'An error was encountered while importing the LTI tool\'s keys from a JWKS URL. '
                    'The RSA keys could not be loaded.'
                )
                raise exceptions.NoSuitableKeys() from err
            keyset.extend(keys.keys)

        if self.public_key:
            # Add to keyset
            keyset.append(self.public_key)

        return keyset

    def validate_and_decode(self, token):
        """
        Check if a message sent by the tool is valid.

        From https://www.imsglobal.org/spec/security/v1p0/#using-oauth-2-0-client-credentials-grant:

        The authorization server decodes the JWT and MUST validate the values for the
        iss, sub, exp, aud and jti claims.
        """
        key_set = self._get_keyset()

        for i, obj in enumerate(key_set):
            try:
                if hasattr(obj.key, 'public_key'):
                    key = obj.key.public_key()
                else:
                    key = obj.key
                message = jwt.decode(
                    token,
                    key,
                    algorithms=['RS256', 'RS512',],
                    options={
                        'verify_signature': True,
                        'verify_aud': False
                    }
                )
                return message
            except Exception:  # pylint: disable=broad-except
                if i == len(key_set) - 1:
                    raise

        raise exceptions.NoSuitableKeys()


class PlatformKeyHandler:
    """
    Platform RSA Key handler.

    This class loads the platform key and is responsible for
    encoding JWT messages and exporting public keys.
    """
    @function_trace('lti_consumer.key_handlers.PlatformKeyHandler.__init__')
    def __init__(self, key_pem, kid=None):
        """
        Import Key when instancing class if a key is present.
        """
        self.key = None

        if key_pem:
            # Import JWK from RSA key
            try:
                algo = jwt.get_algorithm_by_name('RS256')
                private_key = algo.prepare_key(key_pem)
                private_jwk = json.loads(algo.to_jwk(private_key))
                private_jwk['kid'] = kid
                self.key = PyJWK.from_dict(private_jwk)
            except jwt.exceptions.InvalidKeyError as err:
                log.warning(
                    'An error was encountered while loading the LTI platform\'s key. '
                    'The RSA key could not be loaded.'
                )
                raise exceptions.InvalidRsaKey() from err

    def encode_and_sign(self, message, expiration=None):
        """
        Encode and sign JSON with RSA key
        """

        if not self.key:
            log.warning(
                'An error was encountered while loading the LTI platform\'s key. '
                'The RSA key is not set.'
            )
            raise exceptions.RsaKeyNotSet()

        _message = copy.deepcopy(message)

        # Set iat and exp if expiration is set
        if expiration:
            _message.update({
                "iat": int(math.floor(time.time())),
                "exp": int(math.floor(time.time()) + expiration),
            })

        # The class instance that sets up the signing operation
        # An RS 256 key is required for LTI 1.3
        return jwt.encode(_message, self.key.key, algorithm="RS256", headers={"kid": self.key.key_id})

    def get_public_jwk(self):
        """
        Export Public JWK
        """
        jwk = {"keys": []}

        # Only append to keyset if a key exists
        if self.key:
            algo_obj = jwt.get_algorithm_by_name('RS256')
            public_key = algo_obj.prepare_key(self.key.key).public_key()
            public_jwk = json.loads(algo_obj.to_jwk(public_key))
            public_jwk['kid'] = self.key.key_id
            jwk['keys'].append(public_jwk)
        return jwk

    def validate_and_decode(self, token, iss=None, aud=None, exp=True):
        """
        Check if a platform token is valid, and return allowed scopes.

        Validates a token sent by the tool using the platform's RSA Key.
        Optionally validate iss and aud claims if provided.
        """
        if not self.key:
            raise exceptions.RsaKeyNotSet()
        try:
            message = jwt.decode(
                token,
                key=self.key.key.public_key(),
                audience=aud,
                issuer=iss,
                algorithms=['RS256', 'RS512'],
                options={
                    'verify_signature': True,
                    'verify_exp': bool(exp),
                    'verify_iss': bool(iss),
                    'verify_aud': bool(aud)
                }
            )
            return message

        except Exception as token_error:
            exc_info = sys.exc_info()
            raise jwt.InvalidTokenError(exc_info[2]) from token_error
