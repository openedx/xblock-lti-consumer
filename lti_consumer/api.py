"""
Python APIs used to handle LTI configuration and launches.

Some methods are meant to be used inside the XBlock, so they
return plaintext to allow easy testing/mocking.
"""
from .models import LtiConfiguration


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


def get_lti_consumer(config_id=None, block=None):
    """
    Retrieves an LTI Consumer instance for a given configuration.

    Returns an instance of LtiConsumer1p1 or LtiConsumer1p3 depending
    on the configuration.
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

    # Return an instance of LTI 1.1 or 1.3 consumer, depending
    # on the configuration stored in the model.
    return lti_config.get_lti_consumer()
