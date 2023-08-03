"""
Compatibility layer to isolate core-platform method calls from implementation.
"""
import logging
from typing import Callable

from django.conf import settings
from django.core.exceptions import ValidationError
from django.forms import ModelForm
from opaque_keys.edx.keys import CourseKey

from lti_consumer.exceptions import LtiError


log = logging.getLogger(__name__)


# Waffle flags configuration

# Namespace
WAFFLE_NAMESPACE = 'lti_consumer'

# Course Waffle Flags
# .. toggle_name: lti_consumer.enable_external_config_filter
# .. toggle_implementation: CourseWaffleFlag
# .. toggle_default: False
# .. toggle_description: Enables fetching of LTI configurations from external
#    sources like plugins using openedx-filters mechanism.
# .. toggle_use_cases: open_edx
# .. toggle_creation_date: 2022-03-31
# .. toggle_tickets: https://github.com/openedx/xblock-lti-consumer/pull/239
# .. toggle_warning: None.
ENABLE_EXTERNAL_CONFIG_FILTER = 'enable_external_config_filter'

# .. toggle_name: lti_consumer.enable_external_user_id_1p1_launches
# .. toggle_implementation: CourseWaffleFlag
# .. toggle_default: False
# .. toggle_description: Enables sending a user's external user ID, as created and stored by the external_user_ids
#    Djangoapp, instead of an anonymous user ID in LTI 1.1 launches.
# .. toggle_use_cases: open_edx
# .. toggle_creation_date: 2022-11-18
# .. toggle_tickets: https://github.com/openedx/xblock-lti-consumer/pull/307
# .. toggle_warning: None.
ENABLE_EXTERNAL_USER_ID_1P1_LAUNCHES = 'enable_external_user_id_1p1_launches'

# Waffle Flags
# .. toggle_name: lti_consumer.enable_database_config
# .. toggle_implementation: CourseWaffleFlag
# .. toggle_default: False
# .. toggle_description: Enables storing and fetching LTI configuration from the database. This should only be enabled
#                        staff members. We do not want to expose the difference between "CONFIG_ON_DB" and
#                        CONFIG_ON_XBLOCK to non-staff Studio users. This flag is provided to allow staff Studio users
#                        to test and setup LTI configurations stored in the database.
# .. toggle_use_cases: open_edx
# .. toggle_creation_date: 2022-06-29
# .. toggle_warning: None.
ENABLE_DATABASE_CONFIG = 'enable_database_config'


def get_external_config_waffle_flag():
    """
    Import and return Waffle flag for enabling external LTI configuration.
    """
    # pylint: disable=import-error,import-outside-toplevel
    from openedx.core.djangoapps.waffle_utils import CourseWaffleFlag
    return CourseWaffleFlag(f'{WAFFLE_NAMESPACE}.{ENABLE_EXTERNAL_CONFIG_FILTER}', __name__)


def get_external_user_id_1p1_launches_waffle_flag():
    """
    Import and return Waffle flag for enabling sending external user IDs in LTI 1.1 launches.
    """
    # pylint: disable=import-error,import-outside-toplevel
    from openedx.core.djangoapps.waffle_utils import CourseWaffleFlag
    return CourseWaffleFlag(f'{WAFFLE_NAMESPACE}.{ENABLE_EXTERNAL_USER_ID_1P1_LAUNCHES}', __name__)


def get_database_config_waffle_flag():
    # pylint: disable=import-error,import-outside-toplevel
    from openedx.core.djangoapps.waffle_utils import CourseWaffleFlag
    return CourseWaffleFlag(f'{WAFFLE_NAMESPACE}.{ENABLE_DATABASE_CONFIG}', __name__)


def load_enough_xblock(location):  # pragma: nocover
    """
    Load enough of an xblock to read from for LTI values stored on the block.
    The block may or may not be bound to the user for actual use depending on
    what has happened in the request so far.
    """
    # pylint: disable=import-error,import-outside-toplevel
    from xmodule.modulestore.django import modulestore

    # Retrieve block from modulestore
    return modulestore().get_item(location)


def load_block_as_user(location):  # pragma: nocover
    """
    Load a block as the current user, or load as the anonymous user if no user is available.
    """
    # pylint: disable=import-error,import-outside-toplevel
    from crum import get_current_user, get_current_request
    from lms.djangoapps.courseware.block_render import get_block_for_descriptor

    # Retrieve block from modulestore
    block = load_enough_xblock(location)
    user = get_current_user()
    request = get_current_request()
    if user and request:
        # If we're in request scope, the block may already be bound to a user
        # and we don't need to do any more loading
        if block.scope_ids.user_id is not None and user.id == block.scope_ids.user_id:
            return block

        # If not load this block to bind it onto the user
        get_block_for_descriptor(
            user=user,
            block=block,
            student_data=None,
            course_key=location.course_key,
            track_function=None,
            request=request,
            field_data_cache=None,
        )
        return block
    else:
        return _load_block_as_anonymous_user(location, block)


def _load_block_as_anonymous_user(location, block):  # pragma: nocover
    """
    Load a block as the anonymous user because no user is available.

    This uses a few internal courseware methods to retrieve the block
    and bind an AnonymousUser to it, in a similar fashion as a `noauth` XBlock
    handler.
    """
    # pylint: disable=import-error,import-outside-toplevel
    from crum import impersonate
    from django.contrib.auth.models import AnonymousUser
    from lms.djangoapps.courseware.block_render import get_block_for_descriptor

    # ensure `crum.get_current_user` returns AnonymousUser. It returns None when outside
    # of request scope which causes error during block loading.
    user = AnonymousUser()
    with impersonate(user):
        # Load block, attaching it to AnonymousUser
        get_block_for_descriptor(
            user=user,
            block=block,
            student_data=None,
            course_key=location.course_key,
            track_function=None,
            request_token="",
            request=None,
            field_data_cache=None,
        )

        return block


def get_user_from_external_user_id(external_user_id):  # pragma: nocover
    """
    Import ExternalId model and find user by external_user_id
    """
    # pylint: disable=import-error,import-outside-toplevel
    from openedx.core.djangoapps.external_user_ids.models import ExternalId
    try:
        external_id = ExternalId.objects.get(
            external_user_id=external_user_id,
            external_id_type__name='lti'
        )
        return external_id.user
    except ExternalId.DoesNotExist as exception:
        raise LtiError('Invalid User') from exception
    except ValidationError as exception:
        raise LtiError('Invalid userID') from exception


def publish_grade(block, user, score, possible,
                  only_if_higher=False, score_deleted=None, comment=None):  # pragma: nocover
    """
    Import grades signals and publishes score by triggering SCORE_PUBLISHED signal.
    """
    # pylint: disable=import-error,import-outside-toplevel
    from lms.djangoapps.grades.api import signals as grades_signals

    # publish score
    grades_signals.SCORE_PUBLISHED.send(
        sender=None,
        block=block,
        user=user,
        raw_earned=score,
        raw_possible=possible,
        only_if_higher=only_if_higher,
        score_deleted=score_deleted,
        grader_response=comment,
    )


def user_has_access(*args, **kwargs):  # pragma: nocover
    """
    Import and run `has_access` from LMS
    """
    # pylint: disable=import-error,import-outside-toplevel
    from lms.djangoapps.courseware.access import has_access
    return has_access(*args, **kwargs)


def user_has_studio_write_access(*args, **kwargs):  # pragma: nocover
    """
    Import and run `has_studio_write_access` from common modules.

    Used to check if someone saving deep linking content has the
    correct write permissions for a given.
    """
    # pylint: disable=import-error,import-outside-toplevel
    from common.djangoapps.student.auth import has_studio_write_access
    return has_studio_write_access(*args, **kwargs)


def get_course_by_id(course_key):  # pragma: nocover
    """
    Import and run `get_course_by_id` from LMS

    TODO: Once the LMS has fully switched over to this new path [1],
    we can remove the legacy (LMS) import support here.

    - [1] https://github.com/openedx/edx-platform/pull/27289
    """
    # pylint: disable=import-outside-toplevel
    try:
        from openedx.core.lib.courses import get_course_by_id as lms_get_course_by_id
    except ImportError:
        from lms.djangoapps.courseware.courses import get_course_by_id as lms_get_course_by_id
    return lms_get_course_by_id(course_key)


def user_course_access(*args, **kwargs):  # pragma: nocover
    """
    Import and run `check_course_access` from LMS
    """
    # pylint: disable=import-error,import-outside-toplevel
    from lms.djangoapps.courseware.courses import check_course_access
    return check_course_access(*args, **kwargs)


def batch_get_or_create_externalids(users):  # pragma: nocover
    """
    Given a list of user, returns corresponding external id's

    External ID's are created when a student actually launches
    LTI from LMS. But when providing course member information
    to a third party tool, not every member has External ID's
    available. To create one by one would be a performance issue.
    This method provides a faster way to create ExternalIds in batch.
    """
    # pylint: disable=import-error,import-outside-toplevel
    from openedx.core.djangoapps.external_user_ids.models import ExternalId
    return ExternalId.batch_get_or_create_user_ids(users, 'lti')


def get_course_members(course_key):  # pragma: nocover
    """
    Returns a dict containing all users associated with the given course
    """
    # pylint: disable=import-error,import-outside-toplevel
    from lms.djangoapps.course_api.api import get_course_members as core_get_course_members
    from lms.djangoapps.course_api.exceptions import OverEnrollmentLimitException

    try:
        return core_get_course_members(course_key)
    except OverEnrollmentLimitException as ex:
        raise LtiError('NRPS is not available for {}'.format(course_key)) from ex


def request_cached(func) -> Callable[[Callable], Callable]:
    """
    Import the `request_cached` decorator from LMS and apply it if available.
    """
    try:
        # pylint: disable=import-outside-toplevel
        from openedx.core.lib.cache_utils import request_cached as lms_request_cached
        return lms_request_cached(func)
    except ImportError:
        log.warning("Unable to import `request_cached`. This is normal if running tests.")
        return func


def clean_course_id(model_form: ModelForm) -> CourseKey:  # pragma: nocover
    """
    Import and run `clean_course_id` from LMS
    """
    # pylint: disable=import-error,import-outside-toplevel
    from openedx.core.lib.courses import clean_course_id as lms_clean_course_id
    return lms_clean_course_id(model_form)


def get_event_tracker():  # pragma: nocover
    """
    Import and return LMS event tracking function
    """
    try:
        # pylint: disable=import-outside-toplevel
        from eventtracking import tracker
        return tracker
    except ModuleNotFoundError:
        return None


def nrps_pii_disallowed():
    """
    Check if platform disallows sharing pii over NRPS
    """
    return (hasattr(settings, 'LTI_NRPS_DISALLOW_PII') and
            settings.LTI_NRPS_DISALLOW_PII is True)
