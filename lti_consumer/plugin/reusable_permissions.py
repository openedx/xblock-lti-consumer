"""Authorization helpers for reusable LTI configuration management."""
from ccx_keys.locator import CCXLocator
from opaque_keys import InvalidKeyError
from opaque_keys.edx.locator import CourseLocator

from lti_consumer.plugin import compat
from lti_consumer.plugin.reusable_keys import normalize_course_key


def can_manage_reusable_context(user, context_type, context_key='', *, course_admin_cache=None):
    """Return whether ``user`` may manage a configuration with this creation context.

    Only a course context can be managed by a non-superuser, and only by an admin
    of that one course. Organization and site contexts are superuser-only. CCX
    courses are superuser-only because Studio's course catalog excludes CCX keys.
    Library and other non-course keys fail closed. ``course_admin_cache`` is
    shared only within a single user's request.
    """
    if not getattr(user, 'is_authenticated', False):
        return False
    if context_type not in ('course', 'organization', 'site'):
        return False
    if context_type in ('organization', 'site'):
        return bool(user.is_superuser)
    if not context_key:
        return False
    try:
        course_key = normalize_course_key(context_key)
    except (InvalidKeyError, TypeError, ValueError):
        return False
    if not isinstance(course_key, CourseLocator):
        return False
    if isinstance(course_key, CCXLocator) and not user.is_superuser:
        return False
    if user.is_superuser:
        return True
    if course_admin_cache is None:
        course_admin_cache = {}
    if course_key not in course_admin_cache:
        course_admin_cache[course_key] = compat.user_is_course_admin(user, course_key)
    return course_admin_cache[course_key]
