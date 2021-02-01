"""
Python APIs used to handle LTI configuration and launches.

Some methods are meant to be used inside the XBlock, so they
return plaintext to allow easy testing/mocking.
"""
from .exceptions import LtiError
from .models import LtiConfiguration, LtiDlContentItem
from .utils import (
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


def get_lti_1p3_launch_info(config_id=None, block=None):
    """
    Retrieves the Client ID, Keyset URL and other urls used to configure a LTI tool.
    """
    # Retrieve LTI Config and consumer
    lti_config = _get_lti_config(config_id, block)
    lti_consumer = lti_config.get_lti_consumer()

    # Check if deep Linking is available, if so, retrieve it's launch url
    deep_linking_launch_url = None
    if lti_consumer.dl is not None:
        deep_linking_launch_url = lti_consumer.prepare_preflight_url(
            callback_url=get_lms_lti_launch_link(),
            hint=lti_config.location,
            lti_hint="deep_linking_launch"
        )

    # Return LTI launch information for end user configuration
    return {
        'client_id': lti_config.lti_1p3_client_id,
        'keyset_url': get_lms_lti_keyset_link(lti_config.location),
        'deployment_id': '1',
        'oidc_callback': get_lms_lti_launch_link(),
        'token_url': get_lms_lti_access_token_link(lti_config.location),
        'deep_linking_launch_url': deep_linking_launch_url,
    }


def get_lti_1p3_launch_start_url(config_id=None, block=None, deep_link_launch=False, hint=""):
    """
    Computes and retrieves the LTI URL that starts the OIDC flow.
    """
    # Retrieve LTI consumer
    lti_config = _get_lti_config(config_id, block)
    lti_consumer = lti_config.get_lti_consumer()

    # Change LTI hint depending on LTI launch type
    lti_hint = ""
    if deep_link_launch:
        lti_hint = "deep_linking_launch"
    else:
        # Check if there's any LTI DL content item
        # This should only yield one result since we
        # don't support multiple content items yet.
        content_items = lti_config.ltidlcontentitem_set.filter(
            content_type=LtiDlContentItem.LTI_RESOURCE_LINK,
        ).only('id')

        if content_items.count():
            lti_hint = f"deep_linking_content_launch:{content_items.get().id}"

    # Prepare and return OIDC flow start url
    return lti_consumer.prepare_preflight_url(
        callback_url=get_lms_lti_launch_link(),
        hint=hint,
        lti_hint=lti_hint
    )


def get_deep_linking_data(deep_linking_id, config_id=None, block=None):
    """
    Retrieves deep linking attributes.

    Only works with a single line item, this is a limitation in the
    current content presentation implementation.
    """
    # Retrieve LTI Configuration
    lti_config = _get_lti_config(config_id, block)
    # Only filter DL content item from content item set in the same LTI configuration.
    # This avoid a malicious user to input a random LTI id and perform LTI DL
    # content launches outsite the scope of it's configuration.
    content_item = lti_config.ltidlcontentitem_set.get(pk=deep_linking_id)
    return content_item.attributes
