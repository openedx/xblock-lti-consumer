"""
LTI 1.3 Consumer implementation
"""
import json
import time

# Quality checks failing due to know pylint bug
# pylint: disable=relative-import
from six.moves.urllib.parse import urlencode

from Crypto.PublicKey import RSA
from jwkest.jwk import RSAKey
from jwkest.jws import JWS
from jwkest import jwk

from .constants import LTI_1P3_ROLE_MAP, LTI_BASE_MESSAGE


class LtiConsumer1p3(object):
    """
    LTI 1.3 Consumer Implementation
    """
    def __init__(
            self,
            iss,
            lti_oidc_url,
            lti_launch_url,
            client_id,
            deployment_id,
            rsa_key,
            rsa_key_id
    ):
        """
        Initialize LTI 1.3 Consumer class
        """
        self.iss = iss
        self.oidc_url = lti_oidc_url
        self.launch_url = lti_launch_url
        self.client_id = client_id
        self.deployment_id = deployment_id

        # Generate JWK from RSA key
        self.jwk = RSAKey(
            # Using the same key ID as client id
            # This way we can easily serve multiple public
            # keys on teh same endpoint and keep all
            # LTI 1.3 blocks working
            kid=rsa_key_id,
            key=RSA.import_key(rsa_key)
        )

        # IMS LTI Claim data
        self.lti_claim_user_data = None
        self.lti_claim_launch_presentation = None
        self.lti_claim_custom_parameters = None

    def _encode_and_sign(self, message):
        """
        Encode and sign JSON with RSA key
        """
        # The class instance that sets up the signing operation
        # An RS 256 key is required for LTI 1.3
        _jws = JWS(message, alg="RS256", cty="JWT")

        # Encode and sign LTI message
        return _jws.sign_compact([self.jwk])

    @staticmethod
    def _get_user_roles(role):
        """
        Converts platform role into LTI compliant roles

        Used in roles claim: should return array of URI values
        for roles that the user has within the message's context.

        Supported roles:
        * Core - Administrator
        * Institution - Instructor (non-core role)
        * Institution - Student

        Reference: http://www.imsglobal.org/spec/lti/v1p3/#roles-claim
        Role vocabularies: http://www.imsglobal.org/spec/lti/v1p3/#role-vocabularies
        """
        lti_user_roles = set()

        if role:
            # Raise value error if value doesn't exist in map
            if role not in LTI_1P3_ROLE_MAP:
                raise ValueError("Invalid role list provided.")

            # Add roles to list
            lti_user_roles.update(LTI_1P3_ROLE_MAP[role])

        return list(lti_user_roles)

    def prepare_preflight_url(
            self,
            callback_url,
            hint="hint",
            lti_hint="lti_hint"
    ):
        """
        Generates OIDC url with parameters
        """
        oidc_url = self.oidc_url + "?"
        parameters = {
            "iss": self.iss,
            "client_id": self.client_id,
            "lti_deployment_id": self.deployment_id,
            "target_link_uri": callback_url,
            "login_hint": hint,
            "lti_message_hint": lti_hint
        }

        return {
            "oidc_url": oidc_url + urlencode(parameters),
        }

    def set_user_data(
            self,
            user_id,
            role,
            full_name=None,
            email_address=None
    ):
        """
        Set user data/roles and convert to IMS Specification

        User Claim doc: http://www.imsglobal.org/spec/lti/v1p3/#user-identity-claims
        Roles Claim doc: http://www.imsglobal.org/spec/lti/v1p3/#roles-claim
        """
        self.lti_claim_user_data = {
            # User identity claims
            # sub: locally stable identifier for user that initiated the launch
            "sub": user_id,

            # Roles claim
            # Array of URI values for roles that the user has within the message's context
            "https://purl.imsglobal.org/spec/lti/claim/roles": self._get_user_roles(role)
        }

        # Additonal user identity claims
        # Optional user data that can be sent to the tool, if the block is configured to do so
        if full_name:
            self.lti_claim_user_data.update({
                "name": full_name,
            })

        if email_address:
            self.lti_claim_user_data.update({
                "email": email_address,
            })

    def set_launch_presentation_claim(
            self,
            document_target="iframe"
    ):
        """
        Optional: Set launch presentation claims

        http://www.imsglobal.org/spec/lti/v1p3/#launch-presentation-claim
        """
        if document_target not in ['iframe', 'frame', 'window']:
            raise ValueError("Invalid launch presentation format.")

        self.lti_claim_launch_presentation = {
            # Launch presentation claim
            "https://purl.imsglobal.org/spec/lti/claim/launch_presentation": {
                # Can be one of: iframe, frame, window
                "document_target": document_target,
                # TODO: Add support for `return_url` handler to allow the tool
                # to return error messages back to the lms.
                # See the spec referenced above for more information.
            },
        }

    def set_custom_parameters(
            self,
            custom_parameters
    ):
        """
        Stores custom parameters configured for LTI launch
        """
        if not isinstance(custom_parameters, dict):
            raise ValueError("Custom parameters must be a key/value dictionary.")

        self.lti_claim_custom_parameters = {
            "https://purl.imsglobal.org/spec/lti/claim/custom": custom_parameters
        }

    def generate_launch_request(
            self,
            preflight_response,
            resource_link
    ):
        """
        Build LTI message from class parameters

        This will add all required parameters from the LTI 1.3 spec and any additional ones set in
        the configuration and JTW encode the message using the provided key.
        """
        # Start from base message
        lti_message = LTI_BASE_MESSAGE.copy()

        # TODO: Validate preflight response
        # Add base parameters
        lti_message.update({
            # Issuer
            "iss": self.iss,

            # Nonce from OIDC preflight launch request
            "nonce": preflight_response.get("nonce"),

            # JWT aud and azp
            "aud": [
                self.client_id
            ],
            "azp": self.client_id,

            # LTI Deployment ID Claim:
            # String that identifies the platform-tool integration governing the message
            # http://www.imsglobal.org/spec/lti/v1p3/#lti-deployment-id-claim
            "https://purl.imsglobal.org/spec/lti/claim/deployment_id": self.deployment_id,

            # Target Link URI: actual endpoint for the LTI resource to display
            # MUST be the same value as the target_link_uri passed by the platform in the OIDC login request
            # http://www.imsglobal.org/spec/lti/v1p3/#target-link-uri
            "https://purl.imsglobal.org/spec/lti/claim/target_link_uri": self.launch_url,

            # Resource link: stable and unique to each deployment_id
            # This value MUST change if the link is copied or exported from one system or
            # context and imported into another system or context
            # http://www.imsglobal.org/spec/lti/v1p3/#resource-link-claim
            "https://purl.imsglobal.org/spec/lti/claim/resource_link": {
                "id": resource_link,
                # Optional claims
                # "title": "Introduction Assignment"
                # "description": "Assignment to introduce who you are",
            },
        })

        # Check if user data is set, then append it to lti message
        # Raise if isn't set, since some user data is required for the launch
        if self.lti_claim_user_data:
            lti_message.update(self.lti_claim_user_data)
        else:
            raise ValueError("Required user data isn't set.")

        # Set optional claims
        # Launch presentation claim
        if self.lti_claim_launch_presentation:
            lti_message.update(self.lti_claim_launch_presentation)

        # Custom variables claim
        if self.lti_claim_custom_parameters:
            lti_message.update(self.lti_claim_custom_parameters)

        # Add `exp` and `iat` JWT attributes
        lti_message.update({
            "iat": int(round(time.time())),
            "exp": int(round(time.time()) + 3600)
        })

        return {
            "state": preflight_response.get("state"),
            "id_token": self._encode_and_sign(lti_message)
        }

    def get_public_keyset(self):
        """
        Export Public JWK
        """
        public_keys = jwk.KEYS()
        public_keys.append(self.jwk)
        return json.loads(public_keys.dump_jwks())
