"""
Python APIs used to handle LTI configuration and launches.

Some methods are meant to be used inside the XBlock, so they
return plaintext to allow easy testing/mocking.
"""

import json

from opaque_keys.edx.keys import CourseKey

from .exceptions import LtiError
from .models import CourseAllowPIISharingInLTIFlag, LtiConfiguration, LtiDlContentItem
from .utils import (
    get_lti_deeplinking_content_url,
    get_lms_lti_keyset_link,
    get_lms_lti_launch_link,
    get_lms_lti_access_token_link,
)


def _get_or_create_local_lti_config(lti_version, block_location):
    """
    Retrieves the id of the LTI Configuration for the
    block and location, or creates one if it doesn't exist.

    Doesn't take into account the LTI version of the cofiguration,
    and updates it accordingly.
    Internal method only since it handles

    Returns LTI configuration.
    """
    lti_config, _ = LtiConfiguration.objects.get_or_create(
        location=block_location,
        config_store=LtiConfiguration.CONFIG_ON_XBLOCK,
    )

    if lti_config.version != lti_version:
        lti_config.version = lti_version
        lti_config.save()

    # Return configuration ID
    return lti_config


def _get_lti_config(config_id=None, block=None):
    """
    Retrieves or creates a LTI Configuration using either block or LTI Config ID.

    This wraps around `_get_or_create_local_lti_config` and handles the block and modulestore
    bits of configuration.
    """
    if config_id:
        lti_config = LtiConfiguration.objects.get(pk=config_id)
    elif block:
        lti_config = _get_or_create_local_lti_config(
            block.lti_version,
            block.location,
        )
        # Since the block was passed, preload it to avoid
        # having to instance the modulestore and fetch it again.
        lti_config.block = block
    else:
        raise LtiError('Either a config_id or block is required to get or create an LTI Configuration.')

    return lti_config


def get_lti_consumer(config_id=None, block=None):
    """
    Retrieves an LTI Consumer instance for a given configuration.

    Returns an instance of LtiConsumer1p1 or LtiConsumer1p3 depending
    on the configuration.
    """
    # Return an instance of LTI 1.1 or 1.3 consumer, depending
    # on the configuration stored in the model.
    return _get_lti_config(config_id, block).get_lti_consumer()


def create_reusable_lti_1p1_configuration():
    lti_config = LtiConfiguration.objects.create(
        version="lti_1p1",
        config_store=LtiConfiguration.CONFIG_ON_DB,
        reusable=True
    )
    return lti_config


def get_reusable_lti_1p1_configurations():
    return LtiConfiguration.objects.filter(
        version="lti_1p1",
        reusable=True,
    )


def get_lti_1p3_launch_info(config_id=None, block=None):
    """
    Retrieves the Client ID, Keyset URL and other urls used to configure a LTI tool.
    """
    # Retrieve LTI Config and consumer
    lti_config = _get_lti_config(config_id, block)
    lti_consumer = lti_config.get_lti_consumer()

    # Check if deep Linking is available, if so, add some extra context:
    # Deep linking launch URL, and if deep linking is already configured
    deep_linking_launch_url = None
    deep_linking_content_items = []

    if lti_consumer.dl is not None:
        deep_linking_launch_url = lti_consumer.prepare_preflight_url(
            callback_url=get_lms_lti_launch_link(),
            hint=lti_config.location,
            lti_hint="deep_linking_launch"
        )

        # Retrieve LTI Content Items (if any was set up)
        dl_content_items = LtiDlContentItem.objects.filter(
            lti_configuration=lti_config
        )
        # Add content item attributes to context
        if dl_content_items.exists():
            deep_linking_content_items = [item.attributes for item in dl_content_items]

    # Return LTI launch information for end user configuration
    return {
        'client_id': lti_config.lti_1p3_client_id,
        'keyset_url': get_lms_lti_keyset_link(lti_config.location),
        'deployment_id': '1',
        'oidc_callback': get_lms_lti_launch_link(),
        'token_url': get_lms_lti_access_token_link(lti_config.location),
        'deep_linking_launch_url': deep_linking_launch_url,
        'deep_linking_content_items':
            json.dumps(deep_linking_content_items, indent=4) if deep_linking_content_items else None,
    }


def get_lti_1p3_launch_start_url(config_id=None, block=None, deep_link_launch=False, dl_content_id=None, hint=""):
    """
    Computes and retrieves the LTI URL that starts the OIDC flow.
    """
    # Retrieve LTI consumer
    lti_config = _get_lti_config(config_id, block)
    lti_consumer = lti_config.get_lti_consumer()

    # Change LTI hint depending on LTI launch type
    lti_hint = ""
    # Case 1: Performs Deep Linking configuration flow. Triggered by staff users to
    # configure tool options and select content to be presented.
    if deep_link_launch:
        lti_hint = "deep_linking_launch"
    # Case 2: Perform a LTI Launch for `ltiResourceLink` content types, since they
    # need to use the launch mechanism from the callback view.
    elif dl_content_id:
        lti_hint = f"deep_linking_content_launch:{dl_content_id}"

    # Prepare and return OIDC flow start url
    return lti_consumer.prepare_preflight_url(
        callback_url=get_lms_lti_launch_link(),
        hint=hint,
        lti_hint=lti_hint
    )


def get_lti_1p3_content_url(config_id=None, block=None, hint=""):
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
    lti_config = _get_lti_config(config_id, block)

    # List content items
    content_items = lti_config.ltidlcontentitem_set.all()

    # If there's no content items, return normal LTI launch URL
    if not content_items.count():
        return get_lti_1p3_launch_start_url(config_id, block, hint=hint)

    # If there's a single `ltiResourceLink` content, return the launch
    # url for that specif deep link
    if content_items.count() == 1 and content_items.get().content_type == LtiDlContentItem.LTI_RESOURCE_LINK:
        return get_lti_1p3_launch_start_url(
            config_id,
            block,
            dl_content_id=content_items.get().id,
            hint=hint,
        )

    # If there's more than one content item, return content presentation URL
    return get_lti_deeplinking_content_url(lti_config.id)


def get_deep_linking_data(deep_linking_id, config_id=None, block=None):
    """
    Retrieves deep linking attributes.

    Only works with a single line item, this is a limitation in the
    current content presentation implementation.
    """
    # Retrieve LTI Configuration
    lti_config = _get_lti_config(config_id, block)
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
