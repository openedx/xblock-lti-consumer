"""
Python APIs used to handle LTI configuration and launches.

Some methods are meant to be used inside the XBlock, so they
return plaintext to allow easy testing/mocking.
"""

import json
from typing import Any

from opaque_keys.edx.keys import CourseKey, UsageKey

from lti_consumer.lti_1p3.constants import LTI_1P3_ROLE_MAP
from lti_consumer.lti_1p3.exceptions import Lti1p3Exception

from .filters import get_external_config_from_filter
from .models import CourseAllowPIISharingInLTIFlag, LtiConfiguration, LtiDlContentItem, LtiXBlockConfig
from .utils import (
    CONFIG_EXTERNAL,
    CONFIG_ON_DB,
    CONFIG_ON_XBLOCK,
    get_cache_key,
    get_data_from_cache,
    get_lms_lti_access_token_link,
    get_lms_lti_keyset_link,
    get_lms_lti_launch_link,
    get_lti_1p3_context_types_claim,
    get_lti_deeplinking_content_url,
    model_to_dict,
)


def _get_or_create_local_lti_xblock_config(
    lti_version: str,
    block_location: UsageKey | str,
    config_id: str | None = None,
    config_store=CONFIG_ON_XBLOCK,
    external_id=None,
):
    """
    Retrieve the LtiConfiguration for the block described by block_location, if one exists. If one does not exist,
    create an LtiConfiguration with the CONFIG_ON_XBLOCK config_store.

    Treat the lti_version argument as the source of truth for LtiConfiguration.version and override the
    LtiConfiguration.version with lti_version. This allows, for example, for
    the XBlock to be the source of truth for the LTI version, which is a user-centric perspective we've adopted.
    This allows XBlock users to update the LTI version without needing to update the database.
    """
    # The create operation is only performed when there is no existing configuration for the block
    lti_xblock_config, created = LtiXBlockConfig.objects.get_or_create(location=block_location)
    lti_config: LtiConfiguration | None = None
    if created:
        if config_id:
            lti_config, _ = LtiConfiguration.objects.get_or_create(config_id=config_id)
        else:
            lti_config = LtiConfiguration.objects.create()
        lti_xblock_config.lti_configuration = lti_config
        lti_xblock_config.save()
    else:
        lti_config = lti_xblock_config.lti_configuration
        if not lti_config or (config_id and lti_config.config_id != config_id):
            # This is an edge case, when an existing configuration is lost or this block is imported from another
            # instance, we create a new configuration to avoid no configuration issue.
            # OR
            # The config_id was changed as a result of author changing the config_store type.
            # In this case we create a copy of the existing configuration with the new config_id.
            lti_config, _ = LtiConfiguration.objects.get_or_create(
                config_id=config_id,
                defaults=model_to_dict(lti_config, ['id', 'config_id', 'location', 'external_config']),
            )
            lti_xblock_config.lti_configuration = lti_config
            lti_xblock_config.save()

    lti_config.config_store = config_store
    lti_config.external_id = external_id

    if lti_config.version != lti_version:
        lti_config.version = lti_version

    lti_config.save()

    return lti_xblock_config


def _get_config_by_config_id(config_id) -> LtiConfiguration:
    """
    Gets the LTI config by its UUID config ID
    """
    return LtiConfiguration.objects.get(config_id=config_id)


def get_lti_config_by_location(location: str, **filters: dict[str, Any]) -> LtiXBlockConfig:
    """
    Gets the LTI xblock config by location
    """
    config = LtiXBlockConfig.objects.get(
        location=location,
        **filters,
    )
    return config


def try_get_config_by_id(config_id) -> LtiConfiguration | None:
    """
    Tries to get the LTI config by its UUID config ID
    """
    try:
        return _get_config_by_config_id(config_id)
    except LtiConfiguration.DoesNotExist:
        return None


def _get_lti_config_for_block(block):
    """
    Retrieves or creates a LTI Xblock Configuration for a block.

    This wraps around `_get_or_create_local_lti_xblock_config` and handles the block and modulestore
    bits of configuration.
    """
    if block.config_type == 'database':
        lti_xblock_config = _get_or_create_local_lti_xblock_config(
            block.lti_version,
            block.scope_ids.usage_id,
            block.config_id,
            CONFIG_ON_DB,
        )
    elif block.config_type == 'external':
        config = get_external_config_from_filter(
            {"course_key": block.scope_ids.usage_id.context_key},
            block.external_config
        )
        lti_xblock_config = _get_or_create_local_lti_xblock_config(
            config.get("version"),
            block.scope_ids.usage_id,
            block.config_id,
            CONFIG_EXTERNAL,
            external_id=block.external_config,
        )
    else:
        lti_xblock_config = _get_or_create_local_lti_xblock_config(
            block.lti_version,
            block.scope_ids.usage_id,
            block.config_id,
            CONFIG_ON_XBLOCK,
        )
    return lti_xblock_config


def config_for_block(block):
    """
    Returns the externally facing config_id of the LTI Configuration used by this block,
    creating one if required. That ID is suitable for use in launch data or get_consumer.
    """
    xblock_config = _get_lti_config_for_block(block)
    return xblock_config


def get_lti_1p3_launch_info(
    launch_data,
    location: UsageKey,
):
    """
    Retrieves the Client ID, Keyset URL and other urls used to configure a LTI tool.
    """
    # Retrieve LTI Config and consumer
    lti_xblock_config = get_lti_config_by_location(
        str(location),
        lti_configuration__config_id=launch_data.config_id,
    )
    lti_consumer = lti_xblock_config.get_lti_consumer()

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
            lti_xblock_config=lti_xblock_config
        )
        # Add content item attributes to context
        if dl_content_items.exists():
            deep_linking_content_items = [item.attributes for item in dl_content_items]

    lti_config = lti_xblock_config.lti_configuration
    if not lti_config:
        raise Lti1p3Exception("LTI configuration not found.")
    config_id = lti_config.config_id
    client_id = lti_config.lti_1p3_client_id
    deployment_id = "1"

    # Display LTI launch information from external configuration.
    # if an external configuration is being used.
    if lti_config.config_store == CONFIG_EXTERNAL and lti_config.external_id:
        external_config = get_external_config_from_filter({}, lti_config.external_id)
        config_id = lti_config.external_id.replace(':', '/')
        client_id = external_config.get('lti_1p3_client_id')
        deployment_id = external_config.get('lti_1p3_deployment_id', deployment_id)

    # Return LTI launch information for end user configuration
    return {
        'client_id': client_id,
        'keyset_url': get_lms_lti_keyset_link(config_id),
        'deployment_id': deployment_id,
        'oidc_callback': get_lms_lti_launch_link(),
        'token_url': get_lms_lti_access_token_link(config_id),
        'deep_linking_launch_url': deep_linking_launch_url,
        'deep_linking_content_items':
            json.dumps(deep_linking_content_items, indent=4) if deep_linking_content_items else None,
    }


def get_lti_1p3_launch_start_url(
    launch_data,
    location: UsageKey,
    deep_link_launch=False,
    dl_content_id=None,
):
    """
    Computes and retrieves the LTI URL that starts the OIDC flow.
    """
    # Retrieve LTI consumer
    lti_xblock_config = get_lti_config_by_location(
        str(location),
        lti_configuration__config_id=launch_data.config_id,
    )
    lti_consumer = lti_xblock_config.get_lti_consumer()

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
    location: UsageKey,
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
    lti_xblock_config = get_lti_config_by_location(
        str(location),
        lti_configuration__config_id=launch_data.config_id,
    )

    # List content items
    content_items = lti_xblock_config.ltidlcontentitem_set.all()

    # If there's no content items, return normal LTI launch URL
    if not content_items.count():
        return get_lti_1p3_launch_start_url(launch_data, location)

    # If there's a single `ltiResourceLink` content, return the launch
    # url for that specific deep link
    if content_items.count() == 1 and content_items.get().content_type == LtiDlContentItem.LTI_RESOURCE_LINK:
        return get_lti_1p3_launch_start_url(
            launch_data,
            location,
            dl_content_id=content_items.get().id,
        )

    # If there's more than one content item, return content presentation URL
    return get_lti_deeplinking_content_url(lti_xblock_config.id, launch_data)


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
