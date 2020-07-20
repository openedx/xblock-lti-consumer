"""
URL mappings for LTI Consumer plugin.
"""

from __future__ import absolute_import

from django.conf import settings
from django.conf.urls import url, include

from rest_framework import routers

from lti_consumer.views import LtiAgsLineItemViewset
from lti_consumer.plugin.views import (
    public_keyset_endpoint,
    launch_gate_endpoint,
    access_token_endpoint
)


# LTI 1.3 APIs router
router = routers.SimpleRouter(trailing_slash=False)
router.register(r'lti-ags', LtiAgsLineItemViewset, basename='lti-ags-view')


urlpatterns = [
    url(
        'lti_consumer/v1/public_keysets/{}$'.format(settings.USAGE_ID_PATTERN),
        public_keyset_endpoint,
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
    url(
        r'lti_consumer/v1/lti/(?P<lti_config_id>[-\w]+)/',
        include(router.urls)
    )
]
