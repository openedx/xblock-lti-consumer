"""LMS-only URLconf for the reusable configuration API tests.

Mirrors the `lms.djangoapp` mount registered in `lti_consumer.apps`, so the
registration metadata rendered by the CMS API can be resolved against the
explicit LMS routes without the CMS management routes.
"""
from django.urls import include, re_path

urlpatterns = [
    re_path(r'^api/', include('lti_consumer.plugin.urls')),
]
