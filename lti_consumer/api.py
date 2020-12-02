"""
Python APIs used to handle LTI configuration and launches.

Some methods are meant to be used inside the XBlock, so they
return plaintext to allow easy testing/mocking.
"""
from .models import LtiConfiguration
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
        raise Exception('Either a config_id or block is required to get or create an LTI Configuration.')

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
    # Retrieve LTI Config
    lti_config = _get_lti_config(config_id, block)

    # Return LTI launch information for end user configuration
    return {
        'client_id': lti_config.lti_1p3_client_id,
        'keyset_url': get_lms_lti_keyset_link(lti_config.location),
        'deployment_id': '1',
        'oidc_callback': get_lms_lti_launch_link(),
        'token_url': get_lms_lti_access_token_link(lti_config.location),
    }


def get_lti_1p3_launch_start_url(config_id=None, block=None, deep_link_launch=False, hint=""):
    """
    Computes and retrieves the LTI URL that starts the OIDC flow.
    """
    # Retrieve LTI consumer
    lti_consumer = get_lti_consumer(config_id, block)

    # Prepare and return OIDC flow start url
    return lti_consumer.prepare_preflight_url(
        callback_url=get_lms_lti_launch_link(),
        hint=hint,
        lti_hint=("deep_linking_launch" if deep_link_launch else "")
    )
