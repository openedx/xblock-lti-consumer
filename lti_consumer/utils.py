# -*- coding: utf-8 -*-
"""
Make '_' a no-op so we can scrape strings
"""


def _(text):
    """
    :return text
    """
    return text


def get_cohort_name(course_key, user):
    try:
        from openedx.core.djangoapps.course_groups.cohorts import get_cohort
        from opaque_keys.edx.keys import CourseKey
    except ImportError:
        return None

    cohort = get_cohort(course_key=CourseKey.from_string(course_key), user=user)
    return cohort.name if cohort else None


def get_team_name(course_key, user):
    from django.conf import settings
    features = getattr(settings, 'FEATURES', {})

    if not features.get('ENABLE_TEAMS'):
        return None

    # No need for handling ImportError, since `ENABLE_TEAMS` is set to True.
    from lms.djangoapps.teams.models import CourseTeamMembership
    from opaque_keys.edx.keys import CourseKey

    try:
        membership = CourseTeamMembership.objects.get(
            user=user,
            team__course_id=CourseKey.from_string(course_key),
        )
    except CourseTeamMembership.DoesNotExist:
        return None

    return membership.team.name
