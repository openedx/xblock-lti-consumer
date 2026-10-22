"""
Test utils
"""
import jwt


def create_jwt(key, message):
    """
    Uses private key to create a JWS from a dict.
    """
    token = jwt.encode(
        message, key.key, algorithm='RS256'
    )
    return token
