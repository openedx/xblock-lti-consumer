"""
LTI 1.3 Consumer implementation
"""
from urllib.parse import urlencode

from lti_consumer.utils import check_token_claim
from . import constants, exceptions
from .constants import (
    LTI_1P3_ROLE_MAP,
    LTI_BASE_MESSAGE,
    LTI_1P3_ACCESS_TOKEN_REQUIRED_CLAIMS,
    LTI_1P3_ACCESS_TOKEN_SCOPES,
    LTI_1P3_CONTEXT_TYPE,
    LTI_PROCTORING_DATA_KEYS,
)
from .key_handlers import ToolKeyHandler, PlatformKeyHandler
from .ags import LtiAgs
from .deep_linking import LtiDeepLinking
from .nprs import LtiNrps


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
            "target_link_uri": self.launch_url,
            "login_hint": hint,
            "lti_message_hint": lti_hint
        }

        return oidc_url + urlencode(parameters)

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

    def get_lti_launch_message(
            self,
            resource_link,
            include_extra_claims=True,
    ):
        """
        Build LTI message from class parameters

        This will add all required parameters from the LTI 1.3 spec and any additional ones set in
        the configuration and JTW encode the message using the provided key.
        """
        # Start from base message
        lti_message = LTI_BASE_MESSAGE.copy()

        # Add base parameters
        lti_message.update({
            # Issuer
            "iss": self.iss,

            # JWT aud and azp
            "aud": self.client_id,
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

        # Only used when doing normal LTI launches
        if include_extra_claims:
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

        return lti_message

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

        # Get LTI Launch Message
        lti_launch_message = self.get_lti_launch_message(resource_link=resource_link)

        # Nonce from OIDC preflight launch request
        lti_launch_message.update({
            "nonce": preflight_response.get("nonce")
        })

        return {
            "state": preflight_response.get("state"),
            "id_token": self.key_handler.encode_and_sign(
                message=lti_launch_message,
                expiration=3600
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
                raise exceptions.MissingRequiredClaim(f'The required claim {required_claim} is missing from the JWT.')

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
            assert response.get("redirect_uri")
            assert response.get("client_id") == self.client_id
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
            return any(scope in allowed_scopes for scope in token_scopes)

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

        # LTI Advantage services
        self.ags = None
        self.dl = None

        # LTI NRPS Variables
        self.nrps = None

    @property
    def lti_ags(self):
        """
        Returns LTI AGS class.
        """
        return self.ags

    @property
    def lti_nrps(self):
        """
        Returns LTI NRPS class.
        """
        return self.nrps

    @property
    def lti_dl(self):
        """
        Returns LTI Deep Linking class.
        """
        return self.dl

    def lti_dl_enabled(self):
        """
        Return whether LTI Deep Linking is enabled.
        """
        lti_dl = self.lti_dl

        if lti_dl:
            return lti_dl
        else:
            return False

    def enable_ags(
        self,
        lineitems_url,
        lineitem_url=None,
        allow_programmatic_grade_interaction=False,
    ):
        """
        Enable LTI Advantage Assignments and Grades Service.

        This will include the LTI AGS Claim in the LTI message
        and set up the required class.
        """

        self.ags = LtiAgs(
            lineitems_url=lineitems_url,
            lineitem_url=lineitem_url,
            allow_creating_lineitems=allow_programmatic_grade_interaction,
            results_service_enabled=True,
            scores_service_enabled=True,
        )

        # Include LTI AGS claim inside the LTI Launch message
        self.set_extra_claim(self.ags.get_lti_ags_launch_claim())

    def enable_deep_linking(
        self,
        deep_linking_launch_url,
        deep_linking_return_url,
    ):
        """
        Enable LTI Advantage Deep Linking Service.

        This will include the LTI DL Claim in the LTI message
        and set up the required class.
        """
        self.dl = LtiDeepLinking(deep_linking_launch_url, deep_linking_return_url)

    def generate_launch_request(
            self,
            preflight_response,
            resource_link
    ):
        """
        Build LTI message for Deep linking launches.

        Overrides method from LtiConsumer1p3 to allow handling LTI Deep linking messages
        """
        # Check if Deep Linking is enabled and that this is a Deep Link Launch
        if self.dl and preflight_response.get("lti_message_hint") == "deep_linking_launch":
            # Validate preflight response
            self._validate_preflight_response(preflight_response)

            # Get LTI Launch Message
            lti_launch_message = self.get_lti_launch_message(
                resource_link=resource_link,
                include_extra_claims=False,
            )

            # Update message type to LtiDeepLinkingRequest,
            # replacing the normal launch request.
            lti_launch_message.update({
                "https://purl.imsglobal.org/spec/lti/claim/message_type": "LtiDeepLinkingRequest",
            })
            # Include deep linking claim
            lti_launch_message.update(
                # TODO: Add extra settings
                self.dl.get_lti_deep_linking_launch_claim()
            )

            # Nonce from OIDC preflight launch request
            lti_launch_message.update({
                "nonce": preflight_response.get("nonce")
            })

            # Return new lanch message, used by XBlock to present the launch
            return {
                "state": preflight_response.get("state"),
                "id_token": self.key_handler.encode_and_sign(
                    message=lti_launch_message,
                    expiration=3600
                )
            }

        # Call LTI Launch if Deep Linking is not
        # set up or this isn't a Deep Link Launch
        return super().generate_launch_request(
            preflight_response,
            resource_link
        )

    def check_and_decode_deep_linking_token(self, token):
        """
        Check and decode Deep Linking response, return selected content items.

        This either returns a content item list or raises an exception.
        """
        if not self.dl:
            raise exceptions.LtiAdvantageServiceNotSetUp()

        # Decode token, check expiration
        deep_link_response = self.tool_jwt.validate_and_decode(token)

        # Check the response is a Deep Linking response type
        message_type = deep_link_response.get("https://purl.imsglobal.org/spec/lti/claim/message_type")
        if not message_type == "LtiDeepLinkingResponse":
            raise exceptions.InvalidClaimValue("Token isn't a Deep Linking Response message.")

        # Check if supported contentitems were returned
        content_items = deep_link_response.get(
            'https://purl.imsglobal.org/spec/lti-dl/claim/content_items',
            # If not found, return empty list
            [],
        )
        if any(
            item['type'] not in constants.LTI_DEEP_LINKING_ACCEPTED_TYPES
            for item in content_items
        ):
            raise exceptions.LtiDeepLinkingContentTypeNotSupported()

        # Return contentitems
        return content_items

    def set_dl_content_launch_parameters(
        self,
        url=None,
        custom=None,
    ):
        """
        Overrides LTI Consumer settings to do content presentation.
        """
        if url:
            self.launch_url = url

        if custom:
            self.set_custom_parameters(custom)

    def enable_nrps(self, context_memberships_url):
        """
        Enable LTI Names and Role Provisioning Service.

        This will include the LTI NRPS Claim in the LTI message
        and set up the required class.
        """

        self.nrps = LtiNrps(context_memberships_url)

        # Include LTI NRPS claim inside the LTI Launch message
        self.set_extra_claim(self.nrps.get_lti_nrps_launch_claim())


class LtiProctoringConsumer(LtiConsumer1p3):
    """
    This class is an LTI Proctoring Services LTI consumer implementation.

    It builds on top of the LtiConsumer1p3r and adds support for the LTI Proctoring Services specification. The
    specification can be found here: http://www.imsglobal.org/spec/proctoring/v1p0.

    This consumer currently only supports the "Assessment Proctoring Messages" and the proctoring assessmen flow.
    It does not currently support the Assessment Control Service.

    The LtiProctoringConsumer requires necessary context to work properly, including data like attempt_number,
    resource_link, etc. This information is provided to the consumer through the set_proctoring_data method, which
    is called from the consuming context to pass in necessary data.
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
        Initialize the LtiProctoringConsumer by delegating to LtiConsumer1p3's __init__ method.
        """
        super().__init__(
            iss,
            lti_oidc_url,
            lti_launch_url,
            client_id,
            deployment_id,
            rsa_key,
            rsa_key_id,
            tool_key,
            tool_keyset_url
        )
        self.proctoring_data = {}

    def set_proctoring_data(self, **kwargs):
        """
        Set the self.proctoring_data dictionary with the provided kwargs, so long as a given key is in
        LTI_PROCTORING_DATA_KEYS.
        """
        for key, value in kwargs.items():
            if key in LTI_PROCTORING_DATA_KEYS:
                self.proctoring_data[key] = value

    def _get_base_claims(self):
        """
        Return claims common to all LTI Proctoring Services LTI launch messages, to be used when creating LTI launch
        messages.
        """
        proctoring_claims = {
            "https://purl.imsglobal.org/spec/lti-ap/claim/attempt_number": self.proctoring_data.get("attempt_number"),
            "https://purl.imsglobal.org/spec/lti-ap/claim/session_data": self.proctoring_data.get("session_data"),
        }

        return proctoring_claims

    def get_start_proctoring_claims(self):
        """
        Return claims specific to LTI Proctoring Services LtiStartProctoring LTI launch message,
        to be injected into the LTI launch message.
        """
        proctoring_claims = self._get_base_claims()
        proctoring_claims.update({
            "https://purl.imsglobal.org/spec/lti/claim/message_type": "LtiStartProctoring",
            "https://purl.imsglobal.org/spec/lti-ap/claim/start_assessment_url":
                self.proctoring_data.get("start_assessment_url"),
        })

        return proctoring_claims

    def get_end_assessment_claims(self):
        """
        Return claims specific to LTI Proctoring Services LtiEndAssessment LTI launch message,
        to be injected into the LTI launch message.
        """
        proctoring_claims = self._get_base_claims()
        proctoring_claims.update({
            "https://purl.imsglobal.org/spec/lti/claim/message_type": "LtiEndAssessment",
        })

        return proctoring_claims

    def generate_launch_request(
        self,
        preflight_response,
        resource_link
    ):
        """
        Build and return LTI launch message for proctoring.

        This method overrides LtiConsumer1p3's method to include proctoring specific launch claims. It leverages
        the set_extra_claim method to include these additional claims in the LTI launch message.
        """
        lti_message_hint = preflight_response.get("lti_message_hint")
        proctoring_claims = None
        if lti_message_hint == "LtiStartProctoring":
            proctoring_claims = self.get_start_proctoring_claims()
        elif lti_message_hint == "LtiEndAssessment":
            proctoring_claims = self.get_end_assessment_claims()
        else:
            raise ValueError('lti_message_hint must be one of [LtiStartProctoring, LtiStartAssessment].')

        self.set_extra_claim(proctoring_claims)

        return super().generate_launch_request(preflight_response, resource_link)

    def check_and_decode_token(self, token):
        """
        Once the Proctoring Tool is satisfied that the user has completed the necessary proctoring set up and that the
        assessment will be proctored securely, it redirects the user to the Assessment Platform, directing the browser
        to make a POST request containing a JWT and the session_data. This is the "Start Assessment" message.

        This method validates the JWT signature and decodes the JWT. It also validates the claims in the JWT according
        to the Proctoring Services specification.

        It either returns a dictionary containing information required by the start_assessment, or it raises an
        exception if any claims is missing or invalid.
        """
        # Decode token and check expiration.
        proctoring_response = self.tool_jwt.validate_and_decode(token)

        # TODO: We MUST perform other forms of validation here.
        # TODO: We MUST validate the verified_user claim if it is provided, although it is optional to provide it.
        #       An Assessment Platform MAY reject the Start Assessment message if a required identity claim is missing
        #       (indicating that it has not been verified by the Proctoring Tool).  Which identity claims a
        #       Proctoring Tool will verify is subject to agreement outside of the scope of this specification but, at a
        #       minimum, it is recommended that Proctoring Tools performing identity verification are able to verify the
        #       given_name, family_name and name claims.
        #       See 3.3 Transferring the Candidate Back to the Assessment Platform.

        # -------------------------
        # Check Required LTI Claims
        # -------------------------

        # Check that the response message_type claim is "LtiStartAssessment".
        claim_key = "https://purl.imsglobal.org/spec/lti/claim/message_type"
        check_token_claim(
            proctoring_response,
            claim_key,
            "LtiStartAssessment",
            f"Token's {claim_key} claim should be LtiStartAssessment."
        )

        # # Check that the response version claim is "1.3.0".
        claim_key = "https://purl.imsglobal.org/spec/lti/claim/version"
        check_token_claim(
            proctoring_response,
            claim_key,
            "1.3.0",
            f"Token's {claim_key} claim should be 1.3.0."
        )

        # Check that the response session_data claim is the correct anti-CSRF token.
        claim_key = "https://purl.imsglobal.org/spec/lti-ap/claim/session_data"
        check_token_claim(
            proctoring_response,
            claim_key,
            self.proctoring_data.get("session_data"),
            f"Token's {claim_key} claim is not correct."
        )

        # TODO: Right now, the library doesn't support additional claims within the resource_link claim.
        #       Once it does, we should check the entire claim instead of just the id.
        claim_key = "https://purl.imsglobal.org/spec/lti/claim/resource_link"
        check_token_claim(
            proctoring_response,
            claim_key,
            {"id": self.proctoring_data.get("resource_link")},
            f"Token's {claim_key} claim is not correct."
        )

        claim_key = "https://purl.imsglobal.org/spec/lti-ap/claim/attempt_number"
        check_token_claim(
            proctoring_response,
            claim_key,
            self.proctoring_data.get("attempt_number"),
            f"Token's {claim_key} claim is not correct."
        )

        # -------------------------
        # Check Optional LTI Claims
        # -------------------------

        verified_user = proctoring_response.get("https://purl.imsglobal.org/spec/lti-ap/claim/verified_user", {})
        # See 4.3.2.1 Verified user claim.
        # The iss and sub attributes SHOULD NOT be included as they are opaque to the Proctoring Tool and cannot be
        # independently verified.
        iss = verified_user.get('iss')
        if iss is not None:
            raise exceptions.InvalidClaimValue('Token verified_user claim should not contain the iss claim.')
        sub = verified_user.get('sub')
        if sub is not None:
            raise exceptions.InvalidClaimValue('Token verified_user claim should not contain the sub claim.')

        # See 4.3.2.1 Verified user claim.
        # If the picture attribute is provided it MUST point to a picture taken by the Proctoring Tool.
        # It MUST NOT be the same picture provided by the Assessment Platform in the Start Proctoring message.
        picture = verified_user.get('picture')
        if picture and picture == self.lti_claim_user_data.get('picture'):
            raise exceptions.InvalidClaimValue(
                'If the verified_claim is provided and contains the picture claim,'
                ' the picture claim should not be the same picture provided by the Assessment Platform to the Tool.'
            )
        # TODO: We can leverage these verified user claims. For example, we could use
        #       these claims for Name Affirmation.

        end_assessment_return = proctoring_response.get(
            "https://purl.imsglobal.org/spec/lti-ap/claim/end_assessment_return"
        )

        response = {
            'end_assessment_return': end_assessment_return,
            'verified_user': verified_user,
        }

        return response
