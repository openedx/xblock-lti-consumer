"""
URL mappings for LTI Consumer plugin.
"""


from django.conf import settings
from django.urls import include, re_path, path
from rest_framework import routers

from lti_consumer.plugin.views import (LtiAgsLineItemViewset,  # LTI Advantage URLs; LTI NRPS URLs
                                       LtiNrpsContextMembershipViewSet, access_token_endpoint,
                                       deep_linking_content_endpoint, deep_linking_response_endpoint,
                                       launch_gate_endpoint, public_keyset_endpoint,
                                       start_proctoring_assessment_endpoint)

# LTI 1.3 APIs router
router = routers.SimpleRouter(trailing_slash=False)
router.register(r'lti-ags', LtiAgsLineItemViewset, basename='lti-ags-view')
router.register(r'memberships', LtiNrpsContextMembershipViewSet, basename='lti-nrps-memberships-view')


app_name = 'lti_consumer'
urlpatterns = [
    path(
        'lti_consumer/v1/public_keysets/<uuid:lti_config_id>',
        public_keyset_endpoint,
        name='lti_consumer.public_keyset_endpoint'
    ),
    re_path(
        f'lti_consumer/v1/public_keysets/{settings.USAGE_ID_PATTERN}$',
        public_keyset_endpoint,
        name='lti_consumer.public_keyset_endpoint_via_location'
    ),
    re_path(
        'lti_consumer/v1/launch/(?:/(?P<suffix>.*))?$',
        launch_gate_endpoint,
        name='lti_consumer.launch_gate'
    ),
    path(
        'lti_consumer/v1/token/<uuid:lti_config_id>',
        access_token_endpoint,
        name='lti_consumer.access_token'
    ),
    re_path(
        f'lti_consumer/v1/token/{settings.USAGE_ID_PATTERN}$',
        access_token_endpoint,
        name='lti_consumer.access_token_via_location'
    ),
    re_path(
        r'lti_consumer/v1/lti/(?P<lti_config_id>[-\w]+)/lti-dl/response',
        deep_linking_response_endpoint,
        name='lti_consumer.deep_linking_response_endpoint'
    ),
    re_path(
        r'lti_consumer/v1/lti/(?P<lti_config_id>[-\w]+)/lti-dl/content',
        deep_linking_content_endpoint,
        name='lti_consumer.deep_linking_content_endpoint'
    ),
    re_path(
        r'lti_consumer/v1/lti/(?P<lti_config_id>[-\w]+)/',
        include(router.urls)
    ),
    path(
        'lti_consumer/v1/start_proctoring_assessment',
        start_proctoring_assessment_endpoint,
        name='lti_consumer.start_proctoring_assessment_endpoint'
    ),
]
