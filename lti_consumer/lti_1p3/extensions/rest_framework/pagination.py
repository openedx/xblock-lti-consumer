"""
Custom Pagination Implementation
"""
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class LinkHeaderPagination(PageNumberPagination):
    """
    Pagination via link header.
    """

    page_size_query_param = "limit"

    def get_paginated_response(self, data):
        """
        Add next and prev page urls to Link header if exists.
        """
        next_page = self.get_next_link()
        prev_page = self.get_previous_link()

        links = [
            (next_page, 'next'),
            (prev_page, 'prev'),
        ]

        header_links = ['<{}>; rel="{}"'.format(link, rel) for link, rel in links if link]

        headers = {'Link': ', '.join(header_links)} if len(header_links) > 0 else {}

        return Response(data, headers=headers)


class LTINRPSMembershipPage:
    """
    This class mimics django paginator page class to support
    the output of `get_course_membership` LMS API.
    """
    def __init__(self, data):
        self.data = data

    def has_next(self):
        """
        Checks if there is a next page.
        """
        return int(self.data['current_page']) < int(self.data['num_pages'])

    def has_previous(self):
        """
        Checks if there is a previous page.
        """
        return int(self.data['current_page']) > 1

    def next_page_number(self):
        """
        Get next page number
        """
        return int(self.data['current_page']) + 1

    def previous_page_number(self):
        """
        Get previous page number
        """
        return int(self.data['current_page']) - 1
