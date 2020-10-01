"""
Django REST Framework extensions for LTI 1.3 & LTI Advantage implementation.

Implements a custom authorization classes to be used by any of the
LTI Advantage extensions.
"""
from rest_framework import permissions


class LtiAgsPermissions(permissions.BasePermission):
    """
    LTI AGS Permissions.

    This checks if the token included in the request
    has the allowed scopes to read/write LTI AGS items
    (LineItems, Results, Score).

    LineItem scopes: https://www.imsglobal.org/spec/lti-ags/v2p0#scope-and-allowed-http-methods
    Results: Not implemented yet.
    Score: Not implemented yet.
    """
    def has_permission(self, request, view):
        """
        Check if LTI AGS permissions are set in auth token.
        """
        has_perm = False

        # Retrieves token from request, which was already checked by
        # the Authentication class, so we assume it's a sane value.
        auth_token = request.headers['Authorization'].split()[1]

        if view.action in ['list', 'retrieve']:
            # We don't need to wrap this around a try-catch because
            # the token was already tested by the Authentication class.
            has_perm = request.lti_consumer.check_token(
                auth_token,
                [
                    'https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly',
                    'https://purl.imsglobal.org/spec/lti-ags/scope/lineitem',
                ],
            )
        elif view.action in ['create', 'update', 'partial_update', 'delete']:
            has_perm = request.lti_consumer.check_token(
                auth_token,
                ['https://purl.imsglobal.org/spec/lti-ags/scope/lineitem']
            )
        return has_perm
