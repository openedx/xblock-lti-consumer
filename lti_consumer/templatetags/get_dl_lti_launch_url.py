"""
Template tags and helper functions for sanitizing html.
"""
from django import template
from lti_consumer.api import get_lti_1p3_launch_start_url
from lti_consumer.plugin import compat

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
    block = None
    if content_item.lti_configuration.location:
        block = compat.load_block_as_anonymous_user(content_item.lti_configuration.location)
    return get_lti_1p3_launch_start_url(
        config_id=content_item.lti_configuration.id,
        block=block,
        dl_content_id=content_item.id,
        hint=str(content_item.lti_configuration.location),
    )
