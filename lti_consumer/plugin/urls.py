"""
URL mappings for LTI Consumer plugin.
"""

from __future__ import absolute_import

from django.conf import settings
from django.conf.urls import url, include
from rest_framework import routers

from .views import (
    get_xblock_handler,
    launch_gate_endpoint,
    access_token_endpoint,
)

urlpatterns = [
    url(
        'lti_consumer/v1/public_keysets/{}$'.format(settings.USAGE_ID_PATTERN),
        get_xblock_handler('public_keyset_endpoint', ['GET']),
        name='lti_consumer.public_keyset_endpoint'
    ),
    url(
        'lti_consumer/v1/launch/(?:/(?P<suffix>.*))?$',
        launch_gate_endpoint,
        name='lti_consumer.launch_gate'
    ),
    url(
        'lti_consumer/v1/token/{}$'.format(settings.USAGE_ID_PATTERN),
        access_token_endpoint,
        name='lti_consumer.access_token'
    ),
    # LTI Adtantage Extension Endpoints
    url(
        'lti_consumer/v1/lti_ags/lineitem/{}$'.format(settings.USAGE_ID_PATTERN),
        get_xblock_handler('lti_ags_lineitem_list', ['GET']),
        name='lti_consumer.lti_ags:list'
    ),
    url(
        'lti_consumer/v1/lti_ags/lineitem/{}/1/$'.format(settings.USAGE_ID_PATTERN),
        get_xblock_handler('lti_ags_lineitem_retrieve', ['GET']),
        name='lti_consumer.lti_ags:retrieve'
    ),
    url(
        'lti_consumer/v1/lti_ags/lineitem/{}/1/results$'.format(settings.USAGE_ID_PATTERN),
        get_xblock_handler('lti_ags_results', ['GET']),
        name='lti_consumer.lti_ags:results'
    ),
]
