from django.conf import settings

from urllib.parse import urlencode

from Crypto.PublicKey import RSA
from jwkest.jwk import RSAKey
from jwkest.jws import JWS
import json
from jwkest import jwk


LTI_BASE_MESSAGE = {
    # Claim type: fixed key with value `LtiResourceLinkRequest`
    # http://www.imsglobal.org/spec/lti/v1p3/#message-type-claim
    "https://purl.imsglobal.org/spec/lti/claim/message_type": "LtiResourceLinkRequest",

    # LTI Claim version
    # http://www.imsglobal.org/spec/lti/v1p3/#lti-version-claim
    "https://purl.imsglobal.org/spec/lti/claim/version": "1.3.0",

    # Optional claims - useless ones
    # "https://purl.imsglobal.org/spec/lti/claim/context": {
    #     "id": "c1d887f0-a1a3-4bca-ae25-c375edcc131a",
    #     "label": "ECON 1010",
    #     "title": "Economics as a Social Science",
    #     "type": ["http://purl.imsglobal.org/vocab/lis/v2/course#CourseOffering"]
    # },
    # "https://purl.imsglobal.org/spec/lti/claim/tool_platform": {
    #     "guid": "ex/48bbb541-ce55-456e-8b7d-ebc59a38d435",
    #     "contact_email": "support@platform.example.edu",
    #     "description": "An Example Tool Platform",
    #     "name": "Example Tool Platform",
    #     "url": "https://platform.example.edu",
    #     "product_family_code": "ExamplePlatformVendor-Product",
    #     "version": "1.0"
    # },

    # Optional claims - Useful
    # This is useful for error redirects
    # http://www.imsglobal.org/spec/lti/v1p3/#launch-presentation-claim
    "https://purl.imsglobal.org/spec/lti/claim/launch_presentation": {
        "document_target": "iframe", # iframe, frame, window
        # Endpoint to redirect the user to after completing LTI task
        # Returns with log statements
        "return_url": "https://platform.example.edu/terms/201601/courses/7/sections/1/resources/2"
    },
    # Custom variables :)
    "https://purl.imsglobal.org/spec/lti/claim/custom": {
        "xstart": "2017-04-21T01:00:00Z",
        "request_url": "https://tool.com/link/123"
    }
}


def generate_oidc_preflight_request(lti_block):
    """
    Generates OIDC url with parameters
    """
    oidc_url = lti_block.lti_1p3_oidc_url + "?"
    parameters = {
        "iss": PLATFORM_ISS,
        "target_link_uri": lti_block.consumer_launch_url,
        "login_hint": "9",
        "lti_message_hint": "123"
    }

    return {
        "oidc_url": oidc_url + urlencode(parameters),
    }

def construct_launch_request(lti_block, preflight_response):
    """
    Construct LTI message
    """
    data = {
        **lti_message,
        "nonce": preflight_response.get("nonce"),
        "aud": ["1"],
    }

    # Wrap it in a JWK class
    _rsajwk = RSAKey(kid="lti_key", key=_rsakey)

    # create the message
    msg = json.dumps(data)

    # The class instance that sets up the signing operation
    _jws = JWS(msg, alg="RS256")

    # Encode and sign LTI message
    return _jws.sign_compact([_rsajwk])


class LtiConsumer1p3:
    def __init__(
            self,
            iss,
            lti_oidc_url,
            lti_launch_url,
            deployment_id,
            rsa_key,
    ):
        self.iss = iss
        self.oidc_url = lti_oidc_url
        self.launch_url = lti_launch_url
        self.deployment_id = deployment_id

        # Generate JWK from RSA key
        self.jwk = RSAKey(
            # Don't hardcode key name
            kid="lti_key",
            key=RSA.import_key(rsa_key)
        )

    def _encode_and_sign(self, message):
        # Dump JSON and encode it with key
        msg = json.dumps(message)

        # The class instance that sets up the signing operation
        # An RS 256 key is required for LTI 1.3
        _jws = JWS(msg, alg="RS256")

        # Encode and sign LTI message
        return _jws.sign_compact([self.jwk])

    @staticmethod
    def _get_user_roles(roles):
        """
        Converts platform roles into LTI compliant roles

        Used in roles claim: should return array of URI values
        for roles that the user has within the message's context.

        Reference: http://www.imsglobal.org/spec/lti/v1p3/#roles-claim
        Role vocabularies: http://www.imsglobal.org/spec/lti/v1p3/#role-vocabularies
        """
        return [
            "http://purl.imsglobal.org/vocab/lis/v2/institution/person#Student",
            "http://purl.imsglobal.org/vocab/lis/v2/membership#Learner",
            "http://purl.imsglobal.org/vocab/lis/v2/membership#Mentor"
        ]

    def preprare_preflight_request(
        self,
        callback_url,
        hint="oidc_hint",
        lti_hint="lti_hint"
    ):
        """
        Generates OIDC url with parameters
        """
        oidc_url = self.oidc_url + "?"
        parameters = {
            "iss": self.iss,
            "target_link_uri": callback_url,
            "login_hint": hint,
            "lti_message_hint": lti_hint
        }

        return {
            "oidc_url": oidc_url + urlencode(parameters),
        }

    def generate_launch_request(
        self,
        user_id,
        roles,
        resource_link,
        preflight_response,
    ):
        data = {
            **LTI_BASE_MESSAGE,

            # Issuer
            "iss": self.iss,

            # Nonce from OIDC preflight launch request
            "nonce": preflight_response.get("nonce"),

            # Todo: fix audience
            "aud": ["openedx"],

            # User identity claims
            # sub: locally stable identifier for user that initiated the launch
            # http://www.imsglobal.org/spec/lti/v1p3/#user-identity-claims
            "sub": user_id,

            # LTI Deployment ID Claim:
            # String that identifies the platform-tool integration governing the message
            # http://www.imsglobal.org/spec/lti/v1p3/#lti-deployment-id-claim
            "https://purl.imsglobal.org/spec/lti/claim/deployment_id": self.deployment_id,

            # Target Link URI: actual endpoint for the LTI resource to display
            # MUST be the same value as the target_link_uri passed by the platform in the OIDC login request
            # http://www.imsglobal.org/spec/lti/v1p3/#target-link-uri
            "https://purl.imsglobal.org/spec/lti/claim/target_link_uri": self.launch_url,

            # Roles claim: array of URI values for roles that the user has within the message's context
            # http://www.imsglobal.org/spec/lti/v1p3/#roles-claim
            "https://purl.imsglobal.org/spec/lti/claim/roles": self._get_user_roles(roles),

            # Resource link: stable and unique to each deployment_id
            # This value MUST change if the link is copied or exported from one system or
            # context and imported into another system or context
            # http://www.imsglobal.org/spec/lti/v1p3/#resource-link-claim
            "https://purl.imsglobal.org/spec/lti/claim/resource_link": {
                "id": resource_link,
                # Optional claims
                # "description": "Assignment to introduce who you are",
                # "title": "Introduction Assignment"
            },

        }

        return {
            "state": preflight_response.get("state"),
            "id_token": self._encode_and_sign(data)
        }

    def get_public_keyset(self):
        """
        Export Public JWK
        """
        public_keys = jwk.KEYS()
        public_keys.append(self.jwk)
        return json.loads(public_keys.dump_jwks())