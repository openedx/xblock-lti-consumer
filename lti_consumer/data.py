"""
This modules provides public data structures to represent LTI 1.3 launch data that can be used within this library and
by users of this library.
"""

from attrs import define, field, validators

from lti_consumer.lti_1p3.constants import LTI_PROCTORING_ASSESSMENT_CONTROL_ACTIONS


@define
class Lti1p3ProctoringLaunchData:
    """
    The Lti1p3ProctoringLaunchData class contains data necessary and related to an LTI 1.3 proctoring launch.
    It is a mechanism to share launch data between apps. Applications using this library should use the
    Lti1p3ProctoringLaunchData class to supply contextually defined or stored launch data to the LTI 1.3 proctoring
    launch.

    Lti1p3ProctoringLaunchData is intended to be initialized and included as an attribute of an instance of the
    Lti1p3LaunchData class.

    * attempt_number (required): The number of the user's attempt in the assessment. The attempt number
        should be an integer that starts with 1 and that is incremented by 1 for each of user's subsequent attempts at
        the assessment.
    * start_assessment_url (conditionally required): The Platform URL that the Tool will send the start
        assessment message to after it has completed the proctoring setup and verification. This attribute is required
        if the message_type attribute of the Lti1p3LaunchData instance is "LtiStartProctoring". It is optional and
        unused otherwise.
    * assessment_control_url (optional): The Platform URL that the Tool will send assessment control messages to.
    * assessment_control_actions (optional): A list of assessment control actions supported by the platform.
    """
    attempt_number = field()
    start_assessment_url = field(default=None)
    assessment_control_url = field(default=None)
    assessment_control_actions = field(
        default=[],
        validator=[validators.deep_iterable(
            member_validator=validators.in_(LTI_PROCTORING_ASSESSMENT_CONTROL_ACTIONS),
            iterable_validator=validators.instance_of(list),
        )],
    )


@define
class Lti1p3LaunchData:
    """
    The Lti1p3LaunchData class contains data necessary and related to an LTI 1.3 launch. It is a mechanism to share
    launch data between apps. Applications using this library should use the Lti1p3LaunchData class to supply
    contextually defined or stored launch data to the generic LTI 1.3 launch.

    * user_id (required): A unique identifier for the user that is requesting the LTI 1.3 launch. If the optional
        attribute external_user_id is provided, user_id will only be used internally and will not be shared externally.
        If external_user_id is not provided, user_id will be shared externally, and then it must be stable to the
        issuer.
    * user_role (required): The user's role as one of the keys in LTI_1P3_ROLE_MAP: staff, instructor, student, or
        guest. It can also be None if the empty list should be sent in the LTI launch message.
    * config_id (required): The config_id field of an LtiConfiguration to use for the launch.
    * resource_link_id (required): A unique identifier that is guaranteed to be unique for each placement of the LTI
        link.
    * preferred_username (optional): The user's username.
    * name (optional): The user's full name.
    * email (optional): The user's email.
    * external_user_id (optional): A unique identifier for the user that is requesting the LTI 1.3 launch that can be
        shared externally. The identifier must be stable to the issuer. This value will be sent to the the Tool in the
        form of both the login_hint in the login initiation request and the sub claim in the ID token of the LTI 1.3
        launch message. Use this attribute to specify what value to send as this claim. Otherwise, the value of the
        required user_id attribute will be used.
    * launch_presentation_document_target (optional): The document_target property of the launch_presentation claim. It
        describes the kind of browser window or frame from which the user launched inside the message sender's system.
        It is one of frame, iframe, or window; it defaults to iframe.
    * launch_presentation_return_url (optional): A URL where the Tool can redirect the learner after the learner
        completes the activity or is unable to start the activity.
    * message_type (optional): The message type of the eventual LTI launch. It defaults to LtiResourceLinkRequest.
    * context_id (conditionally required): The id property of the context claim. It is the stable, unique identifier for
        the context. It is required if any of the context properties are provided.
    * context_type (optional): The type property of the context claim. It is a list of some combination of the following
        valid context_types: group, course_offering, course_section, or course_template.
    * context_title (optional): The title proerty of the context claim. It is a short, descriptive name for the context.
    * context_label (optional): The label property of the context claim. It is a full, descriptive name for the context.
    * deep_linking_context_item_id (optional): The database id of the LtiDlContentItem that should be used for the LTI
        1.3 Deep Linking launch. It is used when the LTI 1.3 Deep Linking launch is a regular LTI resource link
        request using a content item that was configured via a previous LTI 1.3 Deep Linking request.
    * proctoring_launch_data (conditionally required): An instance of the Lti1p3ProctoringLaunchData that contains
        data necessary and related to an LTI 1.3 proctoring launch. It is required if the message_type attribute is
        "LtiStartProctoring" or "LtiEndAssessment".
    """
    user_id = field()
    user_role = field()
    config_id = field()
    resource_link_id = field()
    preferred_username = field(default=None)
    name = field(default=None)
    email = field(default=None)
    external_user_id = field(default=None)
    launch_presentation_document_target = field(default=None)
    launch_presentation_return_url = field(default=None)
    message_type = field(default="LtiResourceLinkRequest")
    context_id = field(default=None)
    context_type = field(default=None)
    context_title = field(default=None)
    context_label = field(default=None)
    deep_linking_content_item_id = field(default=None)
    proctoring_launch_data = field(
        default=None,
        validator=validators.optional((validators.instance_of(Lti1p3ProctoringLaunchData))),
    )
