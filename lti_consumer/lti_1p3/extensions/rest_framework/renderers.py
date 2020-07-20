"""
LTI 1.3 Django extensions - Content renderers

Used by DRF views to render content in LTI APIs.
"""
from rest_framework import renderers


class LineItemsRenderer(renderers.JSONRenderer):
    """
    Line Items Renderer.

    It's a JSON parser, but uses a custom media_type.
    Reference: https://www.imsglobal.org/spec/lti-ags/v2p0#media-types-and-schemas
    """
    media_type = 'application/vnd.ims.lis.v2.lineitemcontainer+json'
    format = 'json'


class LineItemRenderer(renderers.JSONRenderer):
    """
    Line Item Renderer.

    It's a JSON parser, but uses a custom media_type.
    Reference: https://www.imsglobal.org/spec/lti-ags/v2p0#media-types-and-schemas
    """
    media_type = 'application/vnd.ims.lis.v2.lineitem+json'
    format = 'json'
