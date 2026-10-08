"""
Template tags and helper functions for sanitizing html.
"""
from django import template
from lti_consumer.api import get_lti_1p3_launch_start_url

register = template.Library()


@register.simple_tag
def get_dl_lti_launch_url(content_item, launch_data):
    """
    Template tag to retrieve the LTI launch URL for `ltiResourceLink` content.

    This uses the LTI Consumer API to generate the LTI 1.3 third party login initiation
    URL to start the LTI 1.3 launch flow.

    This template tag requires content_item and launch_data arguments, which are passed to
    get_lti_1p3_launch_start_url to encode information necessary to the eventual LTI 1.3 launch.
    """
    return get_lti_1p3_launch_start_url(
        launch_data,
        dl_content_id=content_item.id,
    )
