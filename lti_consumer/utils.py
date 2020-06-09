# -*- coding: utf-8 -*-
"""
Utility functions for LTI Consumer block
"""
from six import text_type
from django.conf import settings


def _(text):
    """
    Make '_' a no-op so we can scrape strings
    """
    return text


def get_lms_base():
    """
    Returns LMS base url to be used as issuer on OAuth2 flows

    TODO: This needs to be improved and account for Open edX sites and
    organizations.
    One possible improvement is to use `contentstore.get_lms_link_for_item`
    and strip the base domain name.
    """
    return settings.LMS_ROOT_URL


def get_lms_lti_keyset_link(location):
    """
    Returns an LMS link to LTI public keyset endpoint

    :param location: the location of the block
    """
    return u"{lms_base}/api/lti_consumer/v1/public_keysets/{location}".format(
        lms_base=get_lms_base(),
        location=text_type(location),
    )


def get_lms_lti_launch_link():
    """
    Returns an LMS link to LTI Launch endpoint

    :param location: the location of the block
    """
    return u"{lms_base}/api/lti_consumer/v1/launch/".format(
        lms_base=get_lms_base(),
    )


def get_lms_lti_access_token_link(location):
    """
    Returns an LMS link to LTI Launch endpoint

    :param location: the location of the block
    """
    return u"{lms_base}/api/lti_consumer/v1/token/{location}".format(
        lms_base=get_lms_base(),
        location=text_type(location),
    )


def get_lms_ags_endpoint(location, pk=None, action=""):
    """
    Returns an LMS link to LTI Launch endpoint

    :param location: the location of the block
    :param pk: unique id of lineitem if being requested
    :param action: path to custom actions, like score and results

    Note: This will be replaced by a Django Viewset on BD-24.
    """
    if pk:
        return u"{lms_base}/api/lti_consumer/v1/lti_ags/{location}/1/{action}".format(
            lms_base=get_lms_base(),
            location=text_type(location),
            action=action
        )

    return u"{lms_base}/api/lti_consumer/v1/lti_ags/{location}".format(
        lms_base=get_lms_base(),
        location=text_type(location),
    )