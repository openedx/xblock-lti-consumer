"""CMS-only URLconf for the reusable configuration API tests.

Mirrors the `cms.djangoapp` mount registered in `lti_consumer.apps`: the
module's real `lti_consumer` namespace under `^api/`, with the LMS endpoints
absent so a CMS request cannot resolve them.
"""
from django.urls import include, re_path

urlpatterns = [
    re_path(r'^api/', include('lti_consumer.plugin.reusable_urls')),
]
