"""CMS URL mappings for reusable LTI configuration management."""
from django.urls import path

from lti_consumer.plugin.reusable_views import (
    ReusableConfigurationDetailView,
    ReusableConfigurationListCreateView,
)

app_name = 'lti_consumer'

urlpatterns = [
    path(
        'lti_consumer/v1/configurations',
        ReusableConfigurationListCreateView.as_view(),
        name='reusable_configuration_create',
    ),
    path(
        'lti_consumer/v1/configurations/<uuid:config_id>',
        ReusableConfigurationDetailView.as_view(),
        name='reusable_configuration_detail',
    ),
]
