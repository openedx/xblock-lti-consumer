"""
Python APIs used to handle LTI configuration and launches.

Some methods are meant to be used inside the XBlock, so they
return plaintext to allow easy testing/mocking.
"""

import json

from opaque_keys.edx.keys import CourseKey

from lti_consumer.lti_1p3.constants import LTI_1P3_ROLE_MAP
from .models import CourseAllowPIISharingInLTIFlag, LtiConfiguration, LtiDlContentItem
from .utils import (
    get_cache_key,
    get_data_from_cache,
    get_lti_1p3_context_types_claim,
    get_lti_deeplinking_content_url,
    get_lms_lti_keyset_link,
    get_lms_lti_launch_link,
    get_lms_lti_access_token_link,
)
from .filters import get_external_config_from_filter


def _get_or_create_local_lti_config(lti_version, block_location,
                                    config_store=LtiConfiguration.CONFIG_ON_XBLOCK, external_id=None):
    """
    Retrieve the LtiConfiguration for the block described by block_location, if one exists. If one does not exist,
    create an LtiConfiguration with the LtiConfiguration.CONFIG_ON_XBLOCK config_store.

    Treat the lti_version argument as the source of truth for LtiConfiguration.version and override the
    LtiConfiguration.version with lti_version. This allows, for example, for
    the XBlock to be the source of truth for the LTI version, which is a user-centric perspective we've adopted.
    This allows XBlock users to update the LTI version without needing to update the database.
    """
    # The create operation is only performed when there is no existing configuration for the block
    lti_config, _ = LtiConfiguration.objects.get_or_create(location=block_location)

    lti_config.config_store = config_store
    lti_config.external_id = external_id

    if lti_config.version != lti_version:
        lti_config.version = lti_version

    lti_config.save()

    return lti_config


def _get_config_by_config_id(config_id):
    """
    Gets the LTI config by its UUID config ID
    """
    return LtiConfiguration.objects.get(config_id=config_id)


def _get_lti_config_for_block(block):
    """
    Retrieves or creates a LTI Configuration for a block.

    This wraps around `_get_or_create_local_lti_config` and handles the block and modulestore
    bits of configuration.
    """
    if block.config_type == 'database':
        lti_config = _get_or_create_local_lti_config(
            block.lti_version,
            block.scope_ids.usage_id,
            LtiConfiguration.CONFIG_ON_DB,
        )
    elif block.config_type == 'external':
        config = get_external_config_from_filter(
            {"course_key": block.scope_ids.usage_id.context_key},
            block.external_config
        )
        lti_config = _get_or_create_local_lti_config(
            config.get("version"),
            block.scope_ids.usage_id,
            LtiConfiguration.CONFIG_EXTERNAL,
            external_id=block.external_config,
        )
    else:
        lti_config = _get_or_create_local_lti_config(
            block.lti_version,
            block.scope_ids.usage_id,
            LtiConfiguration.CONFIG_ON_XBLOCK,
        )
    return lti_config


def config_id_for_block(block):
    """
    Returns the externally facing config_id of the LTI Configuration used by this block,
    creating one if required. That ID is suitable for use in launch data or get_consumer.
    """
    config = _get_lti_config_for_block(block)
    return config.config_id


def get_lti_consumer(config_id):
    """
    Retrieves an LTI Consumer instance for a given configuration.

    Returns an instance of LtiConsumer1p1 or LtiConsumer1p3 depending
    on the configuration.
    """
    # Return an instance of LTI 1.1 or 1.3 consumer, depending
    # on the configuration stored in the model.
    return _get_config_by_config_id(config_id).get_lti_consumer()


def get_lti_1p3_launch_info(
    launch_data,
):
    """
    Retrieves the Client ID, Keyset URL and other urls used to configure a LTI tool.
    """
    # Retrieve LTI Config and consumer
    lti_config = _get_config_by_config_id(launch_data.config_id)
    lti_consumer = lti_config.get_lti_consumer()

    # Check if deep Linking is available, if so, add some extra context:
    # Deep linking launch URL, and if deep linking is already configured
    deep_linking_launch_url = None
    deep_linking_content_items = []

    deep_linking_enabled = lti_consumer.lti_dl_enabled()

    if deep_linking_enabled:
        launch_data.message_type = "LtiDeepLinkingRequest"
        deep_linking_launch_url = lti_consumer.prepare_preflight_url(
            launch_data,
        )

        # Retrieve LTI Content Items (if any was set up)
        dl_content_items = LtiDlContentItem.objects.filter(
            lti_configuration=lti_config
        )
        # Add content item attributes to context
        if dl_content_items.exists():
            deep_linking_content_items = [item.attributes for item in dl_content_items]

    config_id = lti_config.config_id

    # Return LTI launch information for end user configuration
    return {
        'client_id': lti_config.lti_1p3_client_id,
        'keyset_url': get_lms_lti_keyset_link(config_id),
        'deployment_id': '1',
        'oidc_callback': get_lms_lti_launch_link(),
        'token_url': get_lms_lti_access_token_link(config_id),
        'deep_linking_launch_url': deep_linking_launch_url,
        'deep_linking_content_items':
            json.dumps(deep_linking_content_items, indent=4) if deep_linking_content_items else None,
    }


def get_lti_1p3_launch_start_url(
    launch_data,
    deep_link_launch=False,
    dl_content_id=None,
):
    """
    Computes and retrieves the LTI URL that starts the OIDC flow.
    """
    # Retrieve LTI consumer
    lti_consumer = get_lti_consumer(launch_data.config_id)

    # Include a message hint in the launch_data depending on LTI launch type
    # Case 1: Performs Deep Linking configuration flow. Triggered by staff users to
    # configure tool options and select content to be presented.
    if deep_link_launch:
        launch_data.message_type = "LtiDeepLinkingRequest"
    # Case 2: Perform a LTI Launch for `ltiResourceLink` content types, since they
    # need to use the launch mechanism from the callback view.
    elif dl_content_id:
        launch_data.deep_linking_content_item_id = dl_content_id

    # Prepare and return OIDC flow start url
    return lti_consumer.prepare_preflight_url(launch_data)


def get_lti_1p3_content_url(
    launch_data,
):
    """
    Computes and returns which URL the LTI consumer should launch to.

    This can return:
    1. A LTI Launch link if:
        a. No deep linking is set
        b. Deep Linking is configured, but a single ltiResourceLink was selected.
    2. The Deep Linking content presentation URL if there's more than one
       Lti DL content in the database.
    """
    # Retrieve LTI consumer
    lti_config = _get_config_by_config_id(launch_data.config_id)

    # List content items
    content_items = lti_config.ltidlcontentitem_set.all()

    # If there's no content items, return normal LTI launch URL
    if not content_items.count():
        return get_lti_1p3_launch_start_url(launch_data)

    # If there's a single `ltiResourceLink` content, return the launch
    # url for that specific deep link
    if content_items.count() == 1 and content_items.get().content_type == LtiDlContentItem.LTI_RESOURCE_LINK:
        return get_lti_1p3_launch_start_url(
            launch_data,
            dl_content_id=content_items.get().id,
        )

    # If there's more than one content item, return content presentation URL
    return get_lti_deeplinking_content_url(lti_config.id, launch_data)


def get_deep_linking_data(deep_linking_id, config_id):
    """
    Retrieves deep linking attributes.

    Only works with a single line item, this is a limitation in the
    current content presentation implementation.
    """
    # Retrieve LTI Configuration
    lti_config = _get_config_by_config_id(config_id)
    # Only filter DL content item from content item set in the same LTI configuration.
    # This avoids a malicious user to input a random LTI id and perform LTI DL
    # content launches outside the scope of its configuration.
    content_item = lti_config.ltidlcontentitem_set.get(pk=deep_linking_id)
    return content_item.attributes


def get_lti_pii_sharing_state_for_course(course_key: CourseKey) -> bool:
    """
    Returns the status of PII sharing for the provided course.

    Args:
        course_key (CourseKey): Course key for the course to check for PII sharing

    Returns:
        bool: The state of PII sharing for this course for LTI.
    """
    return CourseAllowPIISharingInLTIFlag.current(course_key).enabled


def validate_lti_1p3_launch_data(launch_data):
    """
    Validate that the data in Lti1p3LaunchData are valid and raise an LtiMessageHintValidationFailure exception if they
    are not.

    The initializer of the Lti1p3LaunchData takes care of ensuring that required data is provided to the class. This
    utility method verifies that other requirements of the data are met.
    """
    validation_messages = []

    # The context claim is an object that composes properties about the context. The claim itself is optional, but if it
    # is provided, then the id property is required. Ensure that if any other of the other optional properties are
    # provided that the id property is also provided.
    if ((launch_data.context_type or launch_data.context_title or launch_data.context_label) and not
            launch_data.context_id):
        validation_messages.append(
            "The context_id attribute is required in the launch data if any optional context properties are provided."
        )

    if launch_data.user_role not in LTI_1P3_ROLE_MAP and launch_data.user_role is not None:
        validation_messages.append(f"The user_role attribute {launch_data.user_role} is not a valid user_role.")

    context_type = launch_data.context_type
    if context_type:
        try:
            get_lti_1p3_context_types_claim(context_type)
        except ValueError:
            validation_messages.append(
                f"The context_type attribute {context_type} in the launch data is not a valid context_type."
            )

    proctoring_launch_data = launch_data.proctoring_launch_data
    if (launch_data.message_type in ["LtiStartProctoring", "LtiEndAssessment"] and not
            proctoring_launch_data):
        validation_messages.append(
            "The proctoring_launch_data attribute is required if the message_type attribute is \"LtiStartProctoring\" "
            "or \"LtiEndAssessment\"."
        )

    if (proctoring_launch_data and launch_data.message_type == "LtiStartProctoring" and not
            proctoring_launch_data.start_assessment_url):
        validation_messages.append(
            "The proctoring_start_assessment_url attribute is required if the message_type attribute is "
            "\"LtiStartProctoring\"."
        )

    if validation_messages:
        return False, validation_messages
    else:
        return True, []


def get_end_assessment_return(user_id, resource_link_id):
    """
    Returns the end_assessment_return value stored in the cache. This can be used by applications to determine whether
    to invoke an LtiEndAssessment LTI launch.

    Arguments:
        * user_id: the database of the requesting User model instance
        * resource_link_id: the resource_link_id of the LTI link for the assessment
    """
    end_assessment_return_key = get_cache_key(
        app="lti",
        key="end_assessment_return",
        user_id=user_id,
        resource_link_id=resource_link_id,
    )
    cached_end_assessment_return = get_data_from_cache(end_assessment_return_key)

    return cached_end_assessment_return
