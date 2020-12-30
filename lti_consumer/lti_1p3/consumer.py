"""
LTI 1.3 Consumer implementation
"""
from urllib.parse import urlencode

from . import exceptions
from .constants import (
    LTI_1P3_ROLE_MAP,
    LTI_BASE_MESSAGE,
    LTI_1P3_ACCESS_TOKEN_REQUIRED_CLAIMS,
    LTI_1P3_ACCESS_TOKEN_SCOPES,
    LTI_1P3_CONTEXT_TYPE,
)
from .key_handlers import ToolKeyHandler, PlatformKeyHandler
from .ags import LtiAgs


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
        self.lti_claim_context = None
        self.lti_claim_custom_parameters = None

        # Extra claims - used by LTI Advantage
        self.extra_claims = {}

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

    def set_context_claim(
            self,
            context_id,
            context_types=None,
            context_title=None,
            context_label=None
    ):
        """
        Optional: Set context claims

        https://www.imsglobal.org/spec/lti/v1p3/#context-claim

        Arguments:
            context_id (string):  Unique value identifying the user
            context_types (list):  A list of context type values for the claim
            context_title (string):  Plain text title of the context
            context_label (string):  Plain text label for the context
        """
        # Set basic claim data
        context_claim_data = {
            "id": context_id,
        }

        # Default context_types to a list if nothing is passed in
        context_types = context_types or []

        # Ensure the value of context_types is a list
        if not isinstance(context_types, list):
            raise TypeError("Invalid type for context_types. It must be a list.")

        # Explicitly ignoring any custom context types
        context_claim_types = [
            context_type.value
            for context_type in context_types
            if isinstance(context_type, LTI_1P3_CONTEXT_TYPE)
        ]

        if context_claim_types:
            context_claim_data["type"] = context_claim_types

        if context_title:
            context_claim_data["title"] = context_title

        if context_label:
            context_claim_data["label"] = context_label

        self.lti_claim_context = {
            # Context claim
            "https://purl.imsglobal.org/spec/lti/claim/context": context_claim_data
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

        # Context claim
        if self.lti_claim_context:
            lti_message.update(self.lti_claim_context)

        # Custom variables claim
        if self.lti_claim_custom_parameters:
            lti_message.update(self.lti_claim_custom_parameters)

        # Extra claims - From LTI Advantage extensions
        if self.extra_claims:
            lti_message.update(self.extra_claims)

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
        return self.key_handler.get_public_jwk()

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
                    "iss": self.iss,
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
        except AssertionError as err:
            raise exceptions.PreflightRequestValidationFailure() from err

    def check_token(self, token, allowed_scopes=None):
        """
        Check if token has access to allowed scopes.
        """
        token_contents = self.key_handler.validate_and_decode(
            token,
            # The issuer of the token is the platform
            iss=self.iss,
        )
        # Tokens are space separated
        token_scopes = token_contents['scopes'].split(' ')

        # Check if token has permission for the requested scope,
        # and throws exception if not.
        # If `allowed_scopes` is empty, return true (just check
        # token validity).
        if allowed_scopes:
            return any(
                [scope in allowed_scopes for scope in token_scopes]
            )

        return True

    def set_extra_claim(self, claim):
        """
        Adds an additional claim to the LTI Launch message
        """
        if not isinstance(claim, dict):
            raise ValueError('Invalid extra claim: is not a dict.')
        self.extra_claims.update(claim)


class LtiAdvantageConsumer(LtiConsumer1p3):
    """
    LTI Advantage  Consumer Implementation.

    Builds on top of the LTI 1.3 consumer and adds support for
    the following LTI Advantage Services:

    * Assignments and Grades Service (LTI-AGS): Allows tools to
      retrieve and send back grades into the platform.
      Note: this is a partial implementation with read-only LineItems.
      Reference spec: https://www.imsglobal.org/spec/lti-ags/v2p0
    """
    def __init__(self, *args, **kwargs):
        """
        Override parent class and set up required LTI Advantage variables.
        """
        super().__init__(*args, **kwargs)

        # LTI AGS Variables
        self.ags = None

    @property
    def lti_ags(self):
        """
        Returns LTI AGS class or throw exception if not set up.
        """
        if not self.ags:
            raise exceptions.LtiAdvantageServiceNotSetUp(
                "The LTI AGS service was not set up for this consumer."
            )

        return self.ags

    def enable_ags(
        self,
        lineitems_url,
        lineitem_url=None,
        allow_programatic_grade_interaction=False,
    ):
        """
        Enable LTI Advantage Assignments and Grades Service.

        This will include the LTI AGS Claim in the LTI message
        and set up the required class.
        """

        self.ags = LtiAgs(
            lineitems_url=lineitems_url,
            lineitem_url=lineitem_url,
            allow_creating_lineitems=allow_programatic_grade_interaction,
            results_service_enabled=True,
            scores_service_enabled=True,
        )

        # Include LTI AGS claim inside the LTI Launch message
        self.set_extra_claim(self.ags.get_lti_ags_launch_claim())
