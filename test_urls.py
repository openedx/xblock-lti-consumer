"""
Custom URL patterns for testing
"""
from django.urls import include, re_path

urlpatterns = [
    re_path(r'^', include('workbench.urls')),
    re_path(r'^', include('lti_consumer.plugin.urls', namespace='lti_consumer')),
]
