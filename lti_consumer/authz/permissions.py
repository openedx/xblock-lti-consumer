"""
Permission checks for reusable LTI configurations.

A configuration is not an authz scope of its own. Its ``context_key`` names the
course run, library, org or instance it belongs to, and every check is made
against the authz scope(s) for that context. Users therefore get permissions on
a configuration from their roles on its context, never from the configuration
itself.

Context keys:

* a course run key, e.g. ``course-v1:MIT+W+2026``
* a library key, e.g. ``lib:MIT:physics``
* ``org:<org>``, e.g. ``org:MIT``
* ``instance``, for the whole Open edX instance
"""

from casbin.util import key_match_func
from openedx_authz.api.data import (
    OrgContentLibraryGlobData,
    OrgCourseOverviewGlobData,
    PlatformContentLibraryGlobData,
    PlatformCourseOverviewGlobData,
)
from openedx_authz.api.users import (
    assign_role_to_user_in_scope,
    get_scopes_for_user_and_permission,
    is_user_allowed,
    unassign_role_from_user,
)

VIEW_CONFIGURATION = "lti_configurations.view_configuration"
CREATE_CONFIGURATION = "lti_configurations.create_configuration"
EDIT_CONFIGURATION = "lti_configurations.edit_configuration"
DELETE_CONFIGURATION = "lti_configurations.delete_configuration"
CONFIGURATION_ACTIONS = {
    "view": VIEW_CONFIGURATION,
    "create": CREATE_CONFIGURATION,
    "edit": EDIT_CONFIGURATION,
    "delete": DELETE_CONFIGURATION,
}

LTI_MANAGER_ROLE = "lti_manager"

ORG_CONTEXT_PREFIX = "org:"
INSTANCE_CONTEXT = "instance"


def org_context(org):
    """
    Return the context key for an organization.
    """
    return f"{ORG_CONTEXT_PREFIX}{org}"


def get_scopes_for_context(context_key):
    """
    Return the authz scope keys that a configuration with this context is checked against.

    Course run and library contexts are their own scope. Org and instance
    contexts span both courses and libraries, which authz keeps in separate
    namespaces, so they map to one glob scope in each.
    """
    if not context_key:
        return []
    if context_key == INSTANCE_CONTEXT:
        return [
            PlatformCourseOverviewGlobData.build_external_key(),
            PlatformContentLibraryGlobData.build_external_key(),
        ]
    if context_key.startswith(ORG_CONTEXT_PREFIX):
        org = context_key[len(ORG_CONTEXT_PREFIX):]
        return [
            OrgCourseOverviewGlobData.build_external_key(org),
            OrgContentLibraryGlobData.build_external_key(org),
        ]
    return [context_key]


def user_has_configuration_permission(user, action, config):
    """
    Return whether ``user`` may perform ``action`` on the configuration ``config``.

    ``action`` is one of the ``lti_configurations.*`` permission names above.
    """
    scopes = get_scopes_for_context(config.context_key)
    if any(is_user_allowed(user.username, action, scope) for scope in scopes):
        return True
    if action == VIEW_CONFIGURATION:
        return _can_view_from_narrower_scope(user, scopes)
    return False


def _can_view_from_narrower_scope(user, config_scopes):
    """
    Let a user view an org or instance configuration from a course run or library where it's available.

    A role on a single course run doesn't match a check at an org glob, so look
    for any scope where the user can view configurations that falls inside one
    of the configuration's scopes.
    """
    user_scopes = get_scopes_for_user_and_permission(user.username, VIEW_CONFIGURATION)
    return any(
        key_match_func(user_scope.external_key, config_scope)
        for user_scope in user_scopes
        for config_scope in config_scopes
    )


def assign_lti_manager(username, context_key):
    """
    Make a user LTI Manager for a context.

    This is a single grant for the person assigning it, but org and instance
    contexts need one authz assignment for courses and one for libraries.
    """
    for scope in get_scopes_for_context(context_key):
        assign_role_to_user_in_scope(username, LTI_MANAGER_ROLE, scope)


def unassign_lti_manager(username, context_key):
    """
    Remove a user's LTI Manager role for a context, undoing :func:`assign_lti_manager`.
    """
    for scope in get_scopes_for_context(context_key):
        unassign_role_from_user(username, LTI_MANAGER_ROLE, scope)
