"""
LTI 1.3 Constants definition file

This includes the LTI Base message, OAuth2 scopes, and
lists of required and optional parameters required for
LTI message generation and validation.
"""
from enum import Enum


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
    ],
    'instructor': [
        'http://purl.imsglobal.org/vocab/lis/v2/institution/person#Instructor',
    ],
    'student': [
        'http://purl.imsglobal.org/vocab/lis/v2/institution/person#Student'
    ],
    'guest': [
        'http://purl.imsglobal.org/vocab/lis/v2/institution/person#Student'
    ],
}


LTI_1P3_ACCESS_TOKEN_REQUIRED_CLAIMS = set([
    "grant_type",
    "client_assertion_type",
    "client_assertion",
    "scope",
])


LTI_1P3_ACCESS_TOKEN_SCOPES = [
    # LTI-AGS Scopes
    'https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly',
    'https://purl.imsglobal.org/spec/lti-ags/scope/lineitem',
    'https://purl.imsglobal.org/spec/lti-ags/scope/result.readonly',
    'https://purl.imsglobal.org/spec/lti-ags/scope/score',
]


class LTI_1P3_CONTEXT_TYPE(Enum):  # pylint: disable=invalid-name
    """ LTI 1.3 Context Claim Types """
    group = 'http://purl.imsglobal.org/vocab/lis/v2/course#CourseGroup'
    course_offering = 'http://purl.imsglobal.org/vocab/lis/v2/course#CourseOffering'
    course_section = 'http://purl.imsglobal.org/vocab/lis/v2/course#CourseSection'
    course_template = 'http://purl.imsglobal.org/vocab/lis/v2/course#CourseTemplate'
