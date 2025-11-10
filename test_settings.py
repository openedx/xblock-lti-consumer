"""
Custom testing settings for testing views
"""
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
