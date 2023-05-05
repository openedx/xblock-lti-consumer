"""
Django REST Framework extensions for LTI 1.3 & LTI Advantage implementation.

Implements a custom authorization classes to be used by any of the
LTI Advantage extensions.
"""
from rest_framework import permissions


class LTIBasePermissions(permissions.BasePermission):
    """
    Base LTI Permissions.

    This checks if the token included in the request
    has the allowed scopes. Allowed scopes should be
    returned by ``get_permission_scopes`` method, which
    should be implemented by child classes.
    """
    def has_permission(self, request, view):
        # Retrieves token from request, which was already checked by
        # the Authentication class, so we assume it's a sane value.
        auth_token = request.headers['Authorization'].split()[1]

        scopes = self.get_permission_scopes(request, view)

        if scopes:
            return request.lti_consumer.check_token(auth_token, scopes)

        return False

    def get_permission_scopes(self, request, view):
        """
        This method should be overriden by child classes to return
        a list of allowed scopes.
        """
        raise NotImplementedError


class LtiAgsPermissions(LTIBasePermissions):
    """
    LTI AGS Permissions.

    This checks if the token included in the request
    has the allowed scopes to read/write LTI AGS items
    (LineItems, Results, Score).

    LineItem scopes: https://www.imsglobal.org/spec/lti-ags/v2p0#scope-and-allowed-http-methods
    Results: Not implemented yet.
    Score: Not implemented yet.
    """

    def get_permission_scopes(self, request, view):
        """
        Return LTI AGS allowed scopes.
        """
        scopes = []
        if view.action in ['list', 'retrieve']:
            # We don't need to wrap this around a try-catch because
            # the token was already tested by the Authentication class.
            scopes = [
                'https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly',
                'https://purl.imsglobal.org/spec/lti-ags/scope/lineitem',
            ]
        elif view.action in ['create', 'update', 'partial_update', 'delete']:
            scopes = [
                'https://purl.imsglobal.org/spec/lti-ags/scope/lineitem',
            ]
        elif view.action in ['results']:
            scopes = [
                'https://purl.imsglobal.org/spec/lti-ags/scope/result.readonly'
            ]
        elif view.action in ['scores']:
            scopes = [
                'https://purl.imsglobal.org/spec/lti-ags/scope/score',
            ]

        return scopes


class LtiNrpsContextMembershipsPermissions(LTIBasePermissions):
    """
    LTI NRPS Context Memberships Permissions.

    This checks if the token included in the request has the allowed scopes to read/write
    the LTI NRPS Context Memberships Service.

    Context Membership scopes: https://www.imsglobal.org/spec/lti-nrps/v2p0#scope-and-service-security
    """

    def get_permission_scopes(self, request, view):
        """
        Return LTI NRPS Context Memberships allowed scopes.
        """
        scopes = []

        if view.action == 'list':
            scopes = [
                'https://purl.imsglobal.org/spec/lti-nrps/scope/contextmembership.readonly'
            ]

        return scopes


class LtiProctoringAcsPermissions(LTIBasePermissions):
    """
    LTI ACS Permissions.

    This checks if the token included in the request
    has the allowed scopes to perform ACS actions
    (insert action examples here)

    Link to relevant docs: (ims global docs url here)
    """

    def get_permission_scopes(self, request, view):
        """
        Return the LTI ACS scope.
        There is only one: http://www.imsglobal.org/spec/proctoring/v1p0#h.ckrfa92a27mw
        """
        return [
            'https://purl.imsglobal.org/spec/lti-ap/scope/control.all',
        ]
