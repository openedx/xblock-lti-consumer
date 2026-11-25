"""LMS-only URLconf for the reusable configuration API tests.

Mirrors the `lms.djangoapp` mount registered in `lti_consumer.apps`, so the
LMS routes resolve without the CMS management routes beside them.
"""
from django.urls import include, re_path

urlpatterns = [
    re_path(r'^api/', include('lti_consumer.plugin.urls')),
]
