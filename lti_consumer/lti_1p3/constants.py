"""
LTI 1.3 Constants definition file

This includes the LTI Base message, OAuth2 scopes, and
lists of required and optional parameters required for
LTI message generation and validation.
"""

LTI_BASE_MESSAGE = {
    # Claim type: fixed key with value `LtiResourceLinkRequest`
    # http://www.imsglobal.org/spec/lti/v1p3/#message-type-claim
    "https://purl.imsglobal.org/spec/lti/claim/message_type": "LtiResourceLinkRequest",

    # LTI Claim version
    # http://www.imsglobal.org/spec/lti/v1p3/#lti-version-claim
    "https://purl.imsglobal.org/spec/lti/claim/version": "1.3.0",
}

LTI_1P3_ROLE_MAP = {
    'staff': [
        'http://purl.imsglobal.org/vocab/lis/v2/system/person#Administrator',
        'http://purl.imsglobal.org/vocab/lis/v2/institution/person#Instructor',
        'http://purl.imsglobal.org/vocab/lis/v2/institution/person#Student',
    ],
    'instructor': [
        'http://purl.imsglobal.org/vocab/lis/v2/institution/person#Instructor',
        'http://purl.imsglobal.org/vocab/lis/v2/institution/person#Student'
    ],
    'student': [
        'http://purl.imsglobal.org/vocab/lis/v2/institution/person#Student'
    ],
    'guest': [
        'http://purl.imsglobal.org/vocab/lis/v2/institution/person#Student'
    ],
}
