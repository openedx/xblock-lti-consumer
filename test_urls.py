"""
Custom URL patterns for testing
"""
from django.urls import include, re_path

urlpatterns = [
    re_path(r'^', include('workbench.urls')),
    re_path(r'^', include('lti_consumer.plugin.urls', namespace='lti_consumer')),
    # Log in to the browsable API as a non-staff user (Django admin login is staff-only).
    re_path(r'^api-auth/', include('rest_framework.urls')),
]
