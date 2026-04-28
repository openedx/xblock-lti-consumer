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

# Role mappings
# Values follow proposed mapping in role matrix.
LTI_1P3_ROLE_BASE = [
    'http://purl.imsglobal.org/vocab/lis/v2/system/person#None',
    'http://purl.imsglobal.org/vocab/lis/v2/institution/person#None',
]

LTI_1P3_CONTEXT_ROLE_INSTRUCTOR = [
    'http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor',
]

LTI_1P3_CONTEXT_ROLE_ADMINISTRATOR = [
    'http://purl.imsglobal.org/vocab/lis/v2/membership#Administrator',
    'http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor',
]

LTI_1P3_SYSTEM_ROLE_ADMINISTRATOR = [
    'http://purl.imsglobal.org/vocab/lis/v2/system/person#Administrator',
]

LTI_1P3_INSTITUTION_ROLE_ADMINISTRATOR = [
    'http://purl.imsglobal.org/vocab/lis/v2/institution/person#Administrator',
    'http://purl.imsglobal.org/vocab/lis/v2/institution/person#Staff',
    'http://purl.imsglobal.org/vocab/lis/v2/institution/person#Faculty',
    'http://purl.imsglobal.org/vocab/lis/v2/institution/person#Instructor',
]

LTI_1P3_CONTEXT_ROLE_LEARNER = [
    'http://purl.imsglobal.org/vocab/lis/v2/membership#Learner',
]

LTI_1P3_CONTEXT_ROLE_TEACHING_ASSISTANT = [
    'http://purl.imsglobal.org/vocab/lis/v2/membership/Instructor#TeachingAssistant',
]

LTI_1P3_ROLE_MAP = {
    'global_staff': (
        LTI_1P3_SYSTEM_ROLE_ADMINISTRATOR
        + LTI_1P3_INSTITUTION_ROLE_ADMINISTRATOR
        + LTI_1P3_CONTEXT_ROLE_ADMINISTRATOR
    ),
    'staff': LTI_1P3_ROLE_BASE + LTI_1P3_CONTEXT_ROLE_INSTRUCTOR,
    'limited_staff': LTI_1P3_ROLE_BASE + LTI_1P3_CONTEXT_ROLE_INSTRUCTOR,
    'instructor': LTI_1P3_ROLE_BASE + LTI_1P3_CONTEXT_ROLE_ADMINISTRATOR,
    'student': LTI_1P3_ROLE_BASE + LTI_1P3_CONTEXT_ROLE_LEARNER,
    'guest': LTI_1P3_ROLE_BASE + LTI_1P3_CONTEXT_ROLE_LEARNER,
    'finance_admin': LTI_1P3_ROLE_BASE + LTI_1P3_CONTEXT_ROLE_LEARNER,
    'sales_admin': LTI_1P3_ROLE_BASE + LTI_1P3_CONTEXT_ROLE_LEARNER,
    'beta_testers': LTI_1P3_ROLE_BASE + LTI_1P3_CONTEXT_ROLE_LEARNER,
    'library_user': LTI_1P3_ROLE_BASE + LTI_1P3_CONTEXT_ROLE_LEARNER,
    'ccx_coach': LTI_1P3_ROLE_BASE + LTI_1P3_CONTEXT_ROLE_LEARNER,
    'data_researcher': LTI_1P3_ROLE_BASE + LTI_1P3_CONTEXT_ROLE_LEARNER,
    'org_course_creator_group': LTI_1P3_ROLE_BASE + LTI_1P3_CONTEXT_ROLE_LEARNER,
    'course_creator_group': LTI_1P3_ROLE_BASE + LTI_1P3_CONTEXT_ROLE_LEARNER,
    'support': LTI_1P3_ROLE_BASE + LTI_1P3_CONTEXT_ROLE_LEARNER,
    'Administrator': LTI_1P3_ROLE_BASE + LTI_1P3_CONTEXT_ROLE_LEARNER,
    'Moderator': LTI_1P3_ROLE_BASE + LTI_1P3_CONTEXT_ROLE_LEARNER,
    'Group Moderator': LTI_1P3_ROLE_BASE + LTI_1P3_CONTEXT_ROLE_LEARNER + LTI_1P3_CONTEXT_ROLE_TEACHING_ASSISTANT,
    'Community TA': LTI_1P3_ROLE_BASE + LTI_1P3_CONTEXT_ROLE_LEARNER + LTI_1P3_CONTEXT_ROLE_TEACHING_ASSISTANT,
    'Student': LTI_1P3_ROLE_BASE + LTI_1P3_CONTEXT_ROLE_LEARNER,
}

# Context membership roles (kept for callers using context map directly)
# https://www.imsglobal.org/spec/lti/v1p3/#lis-vocabulary-for-context-roles
LTI_1P3_CONTEXT_ROLE_MAP = {
    'global_staff': LTI_1P3_CONTEXT_ROLE_ADMINISTRATOR,
    'staff': LTI_1P3_CONTEXT_ROLE_INSTRUCTOR,
    'limited_staff': LTI_1P3_CONTEXT_ROLE_INSTRUCTOR,
    'instructor': LTI_1P3_CONTEXT_ROLE_ADMINISTRATOR,
    'student': LTI_1P3_CONTEXT_ROLE_LEARNER,
    'guest': LTI_1P3_CONTEXT_ROLE_LEARNER,
    'finance_admin': LTI_1P3_CONTEXT_ROLE_LEARNER,
    'sales_admin': LTI_1P3_CONTEXT_ROLE_LEARNER,
    'beta_testers': LTI_1P3_CONTEXT_ROLE_LEARNER,
    'library_user': LTI_1P3_CONTEXT_ROLE_LEARNER,
    'ccx_coach': LTI_1P3_CONTEXT_ROLE_LEARNER,
    'data_researcher': LTI_1P3_CONTEXT_ROLE_LEARNER,
    'org_course_creator_group': LTI_1P3_CONTEXT_ROLE_LEARNER,
    'course_creator_group': LTI_1P3_CONTEXT_ROLE_LEARNER,
    'support': LTI_1P3_CONTEXT_ROLE_LEARNER,
    'Administrator': LTI_1P3_CONTEXT_ROLE_LEARNER,
    'Moderator': LTI_1P3_CONTEXT_ROLE_LEARNER,
    'Group Moderator': LTI_1P3_CONTEXT_ROLE_LEARNER + LTI_1P3_CONTEXT_ROLE_TEACHING_ASSISTANT,
    'Community TA': LTI_1P3_CONTEXT_ROLE_LEARNER + LTI_1P3_CONTEXT_ROLE_TEACHING_ASSISTANT,
    'Student': LTI_1P3_CONTEXT_ROLE_LEARNER,
}

LTI_1P3_ACCESS_TOKEN_REQUIRED_CLAIMS = {
    "grant_type",
    "client_assertion_type",
    "client_assertion",
    "scope",
}


LTI_1P3_ACCESS_TOKEN_SCOPES = [
    # LTI-AGS Scopes
    'https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly',
    'https://purl.imsglobal.org/spec/lti-ags/scope/lineitem',
    'https://purl.imsglobal.org/spec/lti-ags/scope/result.readonly',
    'https://purl.imsglobal.org/spec/lti-ags/scope/score',

    # LTI-NRPS Scopes
    'https://purl.imsglobal.org/spec/lti-nrps/scope/contextmembership.readonly',
]

LTI_1P3_ACS_SCOPE = 'https://purl.imsglobal.org/spec/lti-ap/scope/control.all'

LTI_DEEP_LINKING_ACCEPTED_TYPES = [
    'ltiResourceLink',
    'link',
    'html',
    'image',
    # TODO: implement "file" support,
]


class LTI_1P3_CONTEXT_TYPE(Enum):  # pylint: disable=invalid-name
    """ LTI 1.3 Context Claim Types """
    group = 'http://purl.imsglobal.org/vocab/lis/v2/course#CourseGroup'
    course_offering = 'http://purl.imsglobal.org/vocab/lis/v2/course#CourseOffering'
    course_section = 'http://purl.imsglobal.org/vocab/lis/v2/course#CourseSection'
    course_template = 'http://purl.imsglobal.org/vocab/lis/v2/course#CourseTemplate'


LTI_PROCTORING_DATA_KEYS = [
    'attempt_number',
    'resource_link_id',
    'session_data',
    'start_assessment_url',
    'assessment_control_url',
    'assessment_control_actions'
]

LTI_PROCTORING_ASSESSMENT_CONTROL_ACTIONS = [
    'pause',
    'resume',
    'terminate',
    'update',
    'flag',
]
