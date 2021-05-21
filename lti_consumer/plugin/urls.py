"""
URL mappings for LTI Consumer plugin.
"""


from django.conf import settings
from django.conf.urls import url, include

from rest_framework import routers

from lti_consumer.plugin.views import (
    public_keyset_endpoint,
    launch_gate_endpoint,
    access_token_endpoint,
    # LTI Advantage URLs
    LtiAgsLineItemViewset,
    deep_linking_response_endpoint,
    deep_linking_content_endpoint,
    # LTI NRPS URLs
    LtiNrpsContextMembershipViewSet,
)


# LTI 1.3 APIs router
router = routers.SimpleRouter(trailing_slash=False)
router.register(r'lti-ags', LtiAgsLineItemViewset, basename='lti-ags-view')
router.register(r'memberships', LtiNrpsContextMembershipViewSet, basename='lti-nrps-memberships-view')


app_name = 'lti_consumer'
urlpatterns = [
    url(
        f'lti_consumer/v1/public_keysets/{settings.USAGE_ID_PATTERN}$',
        public_keyset_endpoint,
        name='lti_consumer.public_keyset_endpoint'
    ),
    url(
        'lti_consumer/v1/launch/(?:/(?P<suffix>.*))?$',
        launch_gate_endpoint,
        name='lti_consumer.launch_gate'
    ),
    url(
        f'lti_consumer/v1/token/{settings.USAGE_ID_PATTERN}$',
        access_token_endpoint,
        name='lti_consumer.access_token'
    ),
    url(
        r'lti_consumer/v1/lti/(?P<lti_config_id>[-\w]+)/lti-dl/response',
        deep_linking_response_endpoint,
        name='lti_consumer.deep_linking_response_endpoint'
    ),
    url(
        r'lti_consumer/v1/lti/(?P<lti_config_id>[-\w]+)/lti-dl/content',
        deep_linking_content_endpoint,
        name='lti_consumer.deep_linking_content_endpoint'
    ),
    url(
        r'lti_consumer/v1/lti/(?P<lti_config_id>[-\w]+)/',
        include(router.urls)
    ),
]
