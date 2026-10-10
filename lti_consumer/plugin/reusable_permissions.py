"""Authorization helpers for reusable LTI configuration management."""
from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import CourseKey
from opaque_keys.edx.locator import CourseLocator

from lti_consumer.plugin import compat


def can_manage_reusable_scope(user, scope, *, course_admin_cache=None):
    """Return whether ``user`` may manage a configuration with this scope.

    Course admins must administer every explicitly scoped course. Organization
    and site-wide scopes are superuser-only. Library scope remains unavailable
    at the management boundary until its authorization/availability policy is
    defined, although the lower-level serializer and storage can parse it.
    ``course_admin_cache`` is shared only within a single user's request.
    """
    if not getattr(user, 'is_authenticated', False) or not isinstance(scope, dict):
        return False

    course_keys = scope.get('course_keys', [])
    organization_keys = scope.get('organization_keys', [])
    site_wide = scope.get('site_wide', False)
    parsed_course_keys = []
    try:
        for value in course_keys:
            course_key = CourseKey.from_string(value)
            if not isinstance(course_key, CourseLocator):
                return False
            parsed_course_keys.append(course_key)
    except (InvalidKeyError, TypeError):
        return False

    if organization_keys or site_wide:
        return bool(user.is_superuser)
    if not parsed_course_keys:
        return False
    if user.is_superuser:
        return True
    if course_admin_cache is None:
        course_admin_cache = {}
    for key in parsed_course_keys:
        if key not in course_admin_cache:
            course_admin_cache[key] = compat.user_is_course_admin(user, key)
        if not course_admin_cache[key]:
            return False
    return True
