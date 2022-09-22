"""
This modules provides public data structures to represent LTI 1.3 launch data that can be used within this library and
by users of this library.
"""

from attrs import define, field


@define
class Lti1p3LaunchData:
    """
    The Lti1p3LaunchData class contains data necessary and related to an LTI 1.3 launch. It is a mechanism to share
    launch data between apps. Applications using this library should use the Lti1p3LaunchData class to supply
    contextually defined or stored launch data to the generic LTI 1.3 launch.

    * user_id (required): the user's unique identifier
    * user_role (required): the user's role as one of the keys in LTI_1P3_ROLE_MAP: staff, instructor, student, or
        guest
    * config_id (required): the config_id field of an LtiConfiguration to use for the launch
    * resource_link_id (required): a unique identifier that is guaranteed to be unique for each placement of the LTI
        link
    * launch_presentation_document_target (optional): the document_target property of the launch_presentation claim; it
        describes the kind of browser window or frame from which the user launched inside the message sender's system;
        it is one of frame, iframe, or window; it defaults to iframe
    * message_type (optional): the message type of the eventual LTI launch; defaults to LtiResourceLinkRequest
    * context_id (conditionally required): the id property of the context claim; the stable, unique identifier for the
        context; if any of the context properties are provided, context_id is required
    * context_type (optional): the type property of the context claim; a list of some combination of the following valid
        context_types: group, course_offering, course_section, or course_template
    * context_title (optional): the title proerty of the context claim; a short, descriptive name for the context
    * context_label (optional): the label property of the context claim; a full, descriptive name for the context
    * deep_linking_context_item_id (optional): the database id of the LtiDlContentItem that should be used for the LTI
        1.3 Deep Linking launch; this is used when the LTI 1.3 Deep Linking launch is a regular LTI resource link
        request using a content item that was configured via a previous LTI 1.3 Deep Linking request
    """
    user_id = field()
    user_role = field()
    config_id = field()
    resource_link_id = field()
    launch_presentation_document_target = field(default="iframe")
    message_type = field(default="LtiResourceLinkRequest")
    context_id = field(default=None)
    context_type = field(default=None)
    context_title = field(default=None)
    context_label = field(default=None)
    deep_linking_content_item_id = field(default=None)
