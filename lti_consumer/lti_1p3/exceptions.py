"""
Custom exceptions for LTI 1.3 consumer

# TODO: Improve exception documentation and output.
"""
# pylint: disable=missing-docstring


class TokenSignatureExpired(Exception):
    pass


class NoSuitableKeys(Exception):
    pass


class UnknownClientId(Exception):
    pass


class MalformedJwtToken(Exception):
    pass


class MissingRequiredClaim(Exception):
    pass


class UnsupportedGrantType(Exception):
    pass


class InvalidRsaKey(Exception):
    pass


class RsaKeyNotSet(Exception):
    pass
