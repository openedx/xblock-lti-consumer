"""CMS URL mappings for reusable LTI configuration management."""
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from lti_consumer.plugin.reusable_views import ReusableConfigurationViewSet

app_name = 'lti_consumer'

# The router supplies the trailing slash and the reusable_configuration-list/-detail
# names ADR 0038 requires. The legacy LMS router keeps its own slashless style.
router = SimpleRouter()
router.register('configurations', ReusableConfigurationViewSet, basename='reusable_configuration')

urlpatterns = [
    path('lti_consumer/v1/', include(router.urls)),
]
