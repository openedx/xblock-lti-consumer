"""
Python APIs used to handle LTI configuration and launches.

Some methods are meant to be used inside the XBlock, so they
return plaintext to allow easy testing/mocking.
"""

import json
import logging

from opaque_keys.edx.keys import CourseKey

from lti_consumer.lti_1p3.constants import LTI_1P3_ROLE_MAP

from .filters import get_external_config_from_filter
from .models import CourseAllowPIISharingInLTIFlag, Lti1p3Passport, LtiConfiguration, LtiDlContentItem
from .utils import (
    get_cache_key,
    get_data_from_cache,
    get_lms_lti_access_token_link,
    get_lms_lti_keyset_link,
    get_lms_lti_launch_link,
    get_lti_1p3_context_types_claim,
    get_lti_deeplinking_content_url,
)

log = logging.getLogger(__name__)


def _ensure_lti_passport(block, lti_config):
    """
    Keep block-backed LTI passport aligned with current block key fields.
    Function updates passport in place when safe, and splits to new passport
    when current passport is shared and active key value changed.

    Flow

    passport missing or non-CONFIG_ON_XBLOCK
        -> return current passport

    passport unshared or tool fields blank
        -> update in place from block if changed
        -> return passport

    passport shared
        -> active tool key mode matches block
           -> return passport
        -> active key mode differs
           -> create new passport
           -> save new passport_id on block
           -> return new passport
    """
    passport = lti_config.lti_1p3_passport
    if not passport or lti_config.config_store != LtiConfiguration.CONFIG_ON_XBLOCK:
        return passport

    block_public_key = str(block.lti_1p3_tool_public_key)
    block_keyset_url = str(block.lti_1p3_tool_keyset_url)

    # Update in place when passport not shared, or when key fields still empty.
    if passport.lticonfiguration_set.count() == 1 or (
        not passport.lti_1p3_tool_public_key and not passport.lti_1p3_tool_keyset_url
    ):
        if passport.lti_1p3_tool_public_key != block_public_key or passport.lti_1p3_tool_keyset_url != block_keyset_url:
            passport.lti_1p3_tool_public_key = block_public_key
            passport.lti_1p3_tool_keyset_url = block_keyset_url
            passport.save()
            log.info("Updated LTI passport for %s", block.scope_ids.usage_id)
        return passport

    # For shared passport, check only active key mode before splitting passport.
    key_mismatch = (
        block.lti_1p3_tool_key_mode == 'public_key' and passport.lti_1p3_tool_public_key != block_public_key
    ) or (
        block.lti_1p3_tool_key_mode == 'keyset_url' and passport.lti_1p3_tool_keyset_url != block_keyset_url
    )

    if key_mismatch:
        from lti_consumer.plugin.compat import save_xblock  # pylint: disable=import-outside-toplevel
        passport = Lti1p3Passport.objects.create(
            lti_1p3_tool_public_key=block_public_key,
            lti_1p3_tool_keyset_url=block_keyset_url,
            name=f"Passport of {block.display_name}",
            context_key=block.context_id,
        )
        # Persist new passport link on block so future loads use split passport.
        block.lti_1p3_passport_id = str(passport.passport_id)
        save_xblock(block)
        log.info("Created new LTI passport for %s", block.scope_ids.usage_id)

    return passport


def _get_or_create_local_lti_config(lti_version, block, config_store=LtiConfiguration.CONFIG_ON_XBLOCK):
    """
    Retrieve or create an LtiConfiguration for the block.

    The lti_version parameter is treated as the source of truth, overriding
    any stored version to allow XBlocks to control LTI version without DB updates.
    """
    lti_config, _ = LtiConfiguration.objects.get_or_create(location=block.scope_ids.usage_id)

    # Ensure passport is synced with block
    passport = _ensure_lti_passport(block, lti_config)

    # Batch updates
    updates = {
        'config_store': config_store,
        'external_id': block.external_config,
        # fallback on block lti_version if lti_version is None
        'version': lti_version or block.lti_version,
    }
    if passport:
        updates['lti_1p3_passport'] = passport

    # Only save if changed
    if any(getattr(lti_config, key) != value for key, value in updates.items()):
        for key, value in updates.items():
            setattr(lti_config, key, value)
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
            block,
            LtiConfiguration.CONFIG_ON_DB,
        )
    elif block.config_type == 'external':
        config = get_external_config_from_filter(
            {"course_key": block.scope_ids.usage_id.context_key},
            block.external_config
        )
        lti_config = _get_or_create_local_lti_config(
            config.get("version"),
            block,
            LtiConfiguration.CONFIG_EXTERNAL,
        )
    else:
        lti_config = _get_or_create_local_lti_config(
            block.lti_version,
            block,
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

    config_id = lti_config.passport_id
    client_id = lti_config.lti_1p3_client_id
    deployment_id = "1"

    # Display LTI launch information from external configuration.
    # if an external configuration is being used.
    if lti_config.config_store == lti_config.CONFIG_EXTERNAL:
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
