"""
Custom exceptions for LTI 1.3 consumer

# TODO: Improve exception documentation and output.
"""


class Lti1p3Exception(Exception):
    """
    This is the base exception for LTI 1.3 related exceptions. LTI 1.3 exceptions should extend this class to provide
    greater detail about the exception.
    """
    message = None

    def __init__(self, message=None):
        if not message:
            message = self.message
        super().__init__(message)


class TokenSignatureExpired(Lti1p3Exception):
    message = "The token signature has expired."


class UnauthorizedToken(Lti1p3Exception):
    pass


class NoSuitableKeys(Lti1p3Exception):
    message = "JWKS could not be loaded from the URL."


class BadJwtSignature(Lti1p3Exception):
    message = "The JWT signature is invalid."


class UnknownClientId(Lti1p3Exception):
    pass


class MalformedJwtToken(Lti1p3Exception):
    message = "The JWT could not be parsed because it is malformed."


class MissingRequiredClaim(Lti1p3Exception):
    message = "The required claim is missing."


class UnsupportedGrantType(Lti1p3Exception):
    message = "The JWT grant_type is unsupported."


class InvalidClaimValue(Lti1p3Exception):
    message = "The claim has an invalid value."


class InvalidRsaKey(Lti1p3Exception):
    message = "The RSA key could not parsed."


class RsaKeyNotSet(Lti1p3Exception):
    message = "The RSA key is not set."


class PreflightRequestValidationFailure(Lti1p3Exception):
    message = "The preflight response is not valid."


class LtiLaunchDataValidationFailure(Lti1p3Exception):
    message = "The Lti1p3LaunchData is not valid."


class LtiAdvantageServiceNotSetUp(Lti1p3Exception):
    message = "The LTI Advantage Service is not set up."


class LtiNrpsServiceNotSetUp(Lti1p3Exception):
    message = "LTI Names and Role Provisioning Services is not set up."


class LtiDeepLinkingContentTypeNotSupported(Lti1p3Exception):
    message = "The content_type is not supported by LTI Deep Linking."
