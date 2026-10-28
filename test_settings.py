"""
Custom testing settings for testing views
"""
import sys

from workbench.settings import *

# We don't need djpyfs for this block so remove it from installed apps.
try:
    INSTALLED_APPS.remove("djpyfs")
except ValueError:
    pass

# Usage id pattern (from edx-platform)
USAGE_ID_PATTERN = r'(?P<usage_id>(?:i4x://?[^/]+/[^/]+/[^/]+/[^@]+(?:@[^/]+)?)|(?:[^/]+))'

# Keep settings, use different ROOT_URLCONF
ROOT_URLCONF = 'test_urls'

# LMS Urls - for LTI 1.3 testing
LMS_ROOT_URL = "https://example.com"
LMS_BASE = "example.com"

# Dummy FEATURES dict
FEATURES = {}

# Set rest framework settings to test pagination
REST_FRAMEWORK = {
    'PAGE_SIZE': 10
}

DEFAULT_HASHING_ALGORITHM = "sha1"

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

# Platform name for LTI 1.1 and 1.3 claims testing
PLATFORM_NAME = "Your platform name here"

# Learning MFE URL for start assessment testing
LEARNING_MICROFRONTEND_URL = 'http://test.learning:2000'

# Mimic running in Studio
SERVICE_VARIANT = 'cms'

# openedx-authz, for reusable LTI configuration permissions. The platform
# provides the course and library models in production; here we use the stub
# models that openedx-authz ships for its own tests.
INSTALLED_APPS += [
    "openedx_authz.engine.apps.CasbinAdapterConfig",
    "openedx_authz.apps.OpenedxAuthzConfig",
    "openedx_authz.tests.stubs.apps.StubsConfig",
    "organizations",
    "waffle",
]
OPENEDX_AUTHZ_CONTENT_LIBRARY_MODEL = "stubs.ContentLibrary"
OPENEDX_AUTHZ_COURSE_OVERVIEW_MODEL = "stubs.CourseOverview"

# Fill in the rest of the openedx-authz defaults (Casbin model, etc.), as the
# platform's plugin settings hook does.
from openedx_authz.settings.common import plugin_settings as authz_plugin_settings  # noqa: E402 pylint: disable=wrong-import-position
authz_plugin_settings(sys.modules[__name__])
