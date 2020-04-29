"""
LTI 1.3 Consumer implementation
"""
import json
import time
from six.moves.urllib.parse import urlencode

from . import exceptions
from .constants import (
    LTI_1P3_ROLE_MAP,
    LTI_BASE_MESSAGE,
    LTI_1P3_ACCESS_TOKEN_REQUIRED_CLAIMS,
    LTI_1P3_ACCESS_TOKEN_SCOPES,
)
from .key_handlers import ToolKeyHandler, PlatformKeyHandler


class LtiConsumer1p3:
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
            rsa_key_id,
            tool_key=None,
            tool_keyset_url=None,
    ):
        """
        Initialize LTI 1.3 Consumer class
        """
        self.iss = iss
        self.oidc_url = lti_oidc_url
        self.launch_url = lti_launch_url
        self.client_id = client_id
        self.deployment_id = deployment_id

        # Set up platform message signature class
        self.key_handler = PlatformKeyHandler(rsa_key, rsa_key_id)

        # Set up tool public key verification class
        self.tool_jwt = ToolKeyHandler(
            public_key=tool_key,
            keyset_url=tool_keyset_url
        )

        # IMS LTI Claim data
        self.lti_claim_user_data = None
        self.lti_claim_launch_presentation = None
        self.lti_claim_custom_parameters = None

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
        # Validate preflight response
        self._validate_preflight_response(preflight_response)

        # Start from base message
        lti_message = LTI_BASE_MESSAGE.copy()

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

        return {
            "state": preflight_response.get("state"),
            "id_token": self.key_handler.encode_and_sign(
                message=lti_message,
                expiration=300
            )
        }

    def get_public_keyset(self):
        """
        Export Public JWK
        """
        public_keys = jwk.KEYS()
        public_keys.append(self.jwk)
        return json.loads(public_keys.dump_jwks())

    def _validate_preflight_response(self, response):
        """
        Validates a preflight response to be used in a launch request

        Raises ValueError in case of validation failure

        :param response: the preflight response to be validated
        """
        try:
            assert response.get("nonce")
            assert response.get("state")
            assert response.get("client_id") == self.client_id
            assert response.get("redirect_uri") == self.launch_url
        except AssertionError:
            raise ValueError("Preflight reponse failed validation")

        return self.key_handler.get_public_jwk()

        public_keys = jwk.KEYS()
        public_keys.append(self.jwk)
        return json.loads(public_keys.dump_jwks())

    def access_token(self, token_request_data):
        """
        Validate request and return JWT access token.

        This complies to IMS Security Framework and accepts a JWT
        as a secret for the client credentials grant.
        See this section:
        https://www.imsglobal.org/spec/security/v1p0/#securing_web_services

        Full spec reference:
        https://www.imsglobal.org/spec/security/v1p0/

        Parameters:
            token_request_data: Dict of parameters sent by LTI tool as form_data.

        Returns:
            A dict containing the JSON response containing a JWT and some extra
            parameters required by LTI tools. This token gives access to all
            supported LTI Scopes from this tool.
        """
        # Check if all required claims are present
        for required_claim in LTI_1P3_ACCESS_TOKEN_REQUIRED_CLAIMS:
            if required_claim not in token_request_data.keys():
                raise exceptions.MissingRequiredClaim()

        # Check that grant type is `client_credentials`
        if token_request_data['grant_type'] != 'client_credentials':
            raise exceptions.UnsupportedGrantType()

        # Validate JWT token
        self.tool_jwt.validate_and_decode(
            token_request_data['client_assertion']
        )

        # Check scopes and only return valid and supported ones
        valid_scopes = []
        requested_scopes = token_request_data['scope'].split(' ')

        for scope in requested_scopes:
            # TODO: Add additional checks for permitted scopes
            # Currently there are no scopes, because there is no use for
            # these access tokens until a tool needs to access the LMS.
            # LTI Advantage extensions make use of this.
            if scope in LTI_1P3_ACCESS_TOKEN_SCOPES:
                valid_scopes.append(scope)

        # Scopes are space separated as described in
        # https://tools.ietf.org/html/rfc6749
        scopes_str = " ".join(valid_scopes)

        # This response is compliant with RFC 6749
        # https://tools.ietf.org/html/rfc6749#section-4.4.3
        return {
            "access_token": self.key_handler.encode_and_sign(
                {
                    "sub": self.client_id,
                    "scopes": scopes_str
                },
                # Create token valid for 3600 seconds (1h) as per specification
                # https://www.imsglobal.org/spec/security/v1p0/#expires_in-values-and-renewing-the-access-token
                expiration=3600
            ),
            "token_type": "bearer",
            "expires_in": 3600,
            "scope": scopes_str
        }

    def _validate_preflight_response(self, response):
        """
        Validates a preflight response to be used in a launch request

        Raises ValueError in case of validation failure

        :param response: the preflight response to be validated
        """
        try:
            assert response.get("nonce")
            assert response.get("state")
            assert response.get("client_id") == self.client_id
            assert response.get("redirect_uri") == self.launch_url
        except AssertionError as e:
            raise ValueError("Preflight reponse failed validation")
