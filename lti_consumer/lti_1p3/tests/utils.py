"""
Test utils
"""
from jwkest.jws import JWS


def create_jwt(key, message):
    """
    Uses private key to create a JWS from a dict.
    """
    jws = JWS(message, alg="RS256", cty="JWT")
    return jws.sign_compact([key])
