"""
Custom exceptions for LTI 1.3 consumer

# TODO: Improve exception documentation and output.
"""


class Lti1p3Exception(Exception):
    pass


class TokenSignatureExpired(Lti1p3Exception):
    pass


class UnauthorizedToken(Lti1p3Exception):
    pass


class NoSuitableKeys(Lti1p3Exception):
    pass


class UnknownClientId(Lti1p3Exception):
    pass


class MalformedJwtToken(Lti1p3Exception):
    pass


class MissingRequiredClaim(Lti1p3Exception):
    pass


class UnsupportedGrantType(Lti1p3Exception):
    pass


class InvalidClaimValue(Lti1p3Exception):
    pass


class InvalidRsaKey(Lti1p3Exception):
    pass


class RsaKeyNotSet(Lti1p3Exception):
    pass


class PreflightRequestValidationFailure(Lti1p3Exception):
    pass


class LtiAdvantageServiceNotSetUp(Lti1p3Exception):
    pass
