"""
Custom URL patterns for testing
"""
from django.conf.urls import include, url

urlpatterns = [
    url(r'^', include('workbench.urls')),
    url(r'^', include('lti_consumer.plugin.urls')),
]
