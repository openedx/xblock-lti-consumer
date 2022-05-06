""" Utilities for the lti_1p3 Djangoapp"""

from lti_consumer.lti_1p3 import exceptions


def check_token_claim(token, claim_key, expected_value, invalid_claim_error_msg):
    """
    Check that the claim in the token with the key claim_key matches the expected value. If not,
    raise an InvalidClaimValue exception with the invalid_claim_error_msg.
    """
    claim_value = token.get(claim_key)

    if claim_value is None:
        raise exceptions.MissingRequiredClaim(f"Token is missing required {claim_key} claim.")
    if claim_value != expected_value:
        raise exceptions.InvalidClaimValue(invalid_claim_error_msg)
