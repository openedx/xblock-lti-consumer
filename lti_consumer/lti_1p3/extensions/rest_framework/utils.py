"""
Utility functions for LTI views
"""
from rest_framework.negotiation import DefaultContentNegotiation


class IgnoreContentNegotiation(DefaultContentNegotiation):
    """
    Helper class to ignore content negotiation on a few rest APIs.

    This is used on views that only return a single content type.  Skips the content
    negotiation step and returns the available content type.
    """

    def select_parser(self, request, parsers):
        """
        Select the first parser in the `.parser_classes` list.
        """
        return parsers[0]

    def select_renderer(self, request, renderers, format_suffix=None):
        """
        Select the first renderer in the `.renderer_classes` list.
        """
        return (renderers[0], renderers[0].media_type)
