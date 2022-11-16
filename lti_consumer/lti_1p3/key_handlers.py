"""
LTI 1.3 - Access token library

This handles validating messages sent by the tool and generating
access token with LTI scopes.
"""
import codecs
import copy
import time
import json

from Cryptodome.PublicKey import RSA
from jwkest import BadSignature, BadSyntax, WrongNumberOfParts, jwk
from jwkest.jwk import RSAKey, load_jwks_from_url
from jwkest.jws import JWS, NoSuitableSigningKeys
from jwkest.jwt import JWT

from . import exceptions


class ToolKeyHandler:
    """
    LTI 1.3 Tool Jwt Handler.

    Uses a tool public keys or keysets URL to retrieve
    a key and validate a message sent by the tool.

    This is primarily used by the Access Token endpoint
    in order to validate the JWT Signature of messages
    signed with the tools signature.
    """
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
                new_key = RSAKey(use='sig')

                # Unescape key before importing it
                raw_key = codecs.decode(public_key, 'unicode_escape')

                # Import Key and save to internal state
                new_key.load_key(RSA.import_key(raw_key))
                self.public_key = new_key
            except ValueError as err:
                raise exceptions.InvalidRsaKey() from err

    def _get_keyset(self, kid=None):
        """
        Get keyset from available sources.

        If using a RSA key, forcefully set the key id
        to match the one from the JWT token.
        """
        keyset = []

        if self.keyset_url:
            try:
                keys = load_jwks_from_url(self.keyset_url)
            except Exception as err:
                # Broad Exception is required here because jwkest raises
                # an Exception object explicitly.
                # Beware that many different scenarios are being handled
                # as an invalid key when the JWK loading fails.
                raise exceptions.NoSuitableKeys() from err
            keyset.extend(keys)

        if self.public_key and kid:
            # Fill in key id of stored key.
            # This is needed because if the JWS is signed with a
            # key with a kid, pyjwkest doesn't match them with
            # keys without kid (kid=None) and fails verification
            self.public_key.kid = kid

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
        try:
            # Get KID from JWT header
            jwt = JWT().unpack(token)

            # Verify message signature
            message = JWS().verify_compact(
                token,
                keys=self._get_keyset(
                    jwt.headers.get('kid')
                )
            )

            # If message is valid, check expiration from JWT
            if 'exp' in message and message['exp'] < time.time():
                raise exceptions.TokenSignatureExpired()

            # TODO: Validate other JWT claims

            # Else returns decoded message
            return message

        except NoSuitableSigningKeys as err:
            raise exceptions.NoSuitableKeys() from err
        except (BadSyntax, WrongNumberOfParts) as err:
            raise exceptions.MalformedJwtToken() from err
        except BadSignature as err:
            raise exceptions.BadJwtSignature() from err


class PlatformKeyHandler:
    """
    Platform RSA Key handler.

    This class loads the platform key and is responsible for
    encoding JWT messages and exporting public keys.
    """
    def __init__(self, key_pem, kid=None):
        """
        Import Key when instancing class if a key is present.
        """
        self.key = None

        if key_pem:
            # Import JWK from RSA key
            try:
                self.key = RSAKey(
                    # Using the same key ID as client id
                    # This way we can easily serve multiple public
                    # keys on teh same endpoint and keep all
                    # LTI 1.3 blocks working
                    kid=kid,
                    key=RSA.import_key(key_pem)
                )
            except ValueError as err:
                raise exceptions.InvalidRsaKey() from err

    def encode_and_sign(self, message, expiration=None):
        """
        Encode and sign JSON with RSA key
        """
        if not self.key:
            raise exceptions.RsaKeyNotSet()

        _message = copy.deepcopy(message)

        # Set iat and exp if expiration is set
        if expiration:
            _message.update({
                "iat": int(round(time.time())),
                "exp": int(round(time.time()) + expiration),
            })

        # The class instance that sets up the signing operation
        # An RS 256 key is required for LTI 1.3
        _jws = JWS(_message, alg="RS256", cty="JWT")

        # Encode and sign LTI message
        return _jws.sign_compact([self.key])

    def get_public_jwk(self):
        """
        Export Public JWK
        """
        public_keys = jwk.KEYS()

        # Only append to keyset if a key exists
        if self.key:
            public_keys.append(self.key)

        return json.loads(public_keys.dump_jwks())

    def validate_and_decode(self, token, iss=None, aud=None):
        """
        Check if a platform token is valid, and return allowed scopes.

        Validates a token sent by the tool using the platform's RSA Key.
        Optionally validate iss and aud claims if provided.
        """
        try:
            # Verify message signature
            message = JWS().verify_compact(token, keys=[self.key])

            # If message is valid, check expiration from JWT
            if 'exp' in message and message['exp'] < time.time():
                raise exceptions.TokenSignatureExpired()

            # Validate issuer claim (if present)
            if iss:
                if 'iss' not in message or message['iss'] != iss:
                    raise exceptions.InvalidClaimValue('The required iss claim is either missing or does '
                                                       'not match the expected iss value.')

            # Validate audience claim (if present)
            if aud:
                if 'aud' not in message or aud not in message['aud']:
                    raise exceptions.InvalidClaimValue('The required aud claim is missing.')

            # Else return token contents
            return message

        except NoSuitableSigningKeys as err:
            raise exceptions.NoSuitableKeys() from err
        except BadSyntax as err:
            raise exceptions.MalformedJwtToken() from err
