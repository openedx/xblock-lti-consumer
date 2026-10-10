"""CMS URL mappings for reusable LTI configuration management."""
from django.urls import path

from lti_consumer.plugin.reusable_views import ReusableConfigurationCreateView

app_name = 'lti_consumer'

urlpatterns = [
    path(
        'lti_consumer/v1/configurations',
        ReusableConfigurationCreateView.as_view(),
        name='reusable_configuration_create',
    ),
]
