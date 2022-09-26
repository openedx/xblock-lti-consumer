"""
Template tags and helper functions for sanitizing html.
"""
from django import template
from lti_consumer.api import get_lti_1p3_launch_start_url


register = template.Library()


@register.filter()
def get_dl_lti_launch_url(content_item):
    """
    Template tag to retrive the LTI launch URL for `ltiResourceLink` content.

    This uses the LTI Consumer API, but hardcodes the `hint` parameter to the
    block id (used when LTI launches are tied to XBlocks).

    TODO: Refactor `hint` to use generic ID once LTI launches out of XBlocks are
    supported.
    """
    #TODO this may have a block dependent config, can it get the block?
    return get_lti_1p3_launch_start_url(
        config_id=content_item.lti_configuration.id,
        dl_content_id=content_item.id,
        hint=str(content_item.lti_configuration.location),
    )
