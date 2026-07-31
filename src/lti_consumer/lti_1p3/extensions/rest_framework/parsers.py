"""
LTI 1.3 Django extensions - Content parsers

Used by DRF views to render content in LTI APIs.
"""

from rest_framework import parsers


class LineItemParser(parsers.JSONParser):
    """
    Line Item Parser.

    It's the same as JSON parser, but uses a custom media_type.
    """
    media_type = 'application/vnd.ims.lis.v2.lineitem+json'


class LineItemScoreParser(parsers.JSONParser):
    """
    Line Item Parser.

    It's the same as JSON parser, but uses a custom media_type.
    """
    media_type = 'application/vnd.ims.lis.v1.score+json'
