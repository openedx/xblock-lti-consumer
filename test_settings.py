"""
Custom testing settings for testing views
"""
from workbench.settings import *


# Usage id pattern (from edx-platform)
USAGE_ID_PATTERN = r'(?P<usage_id>(?:i4x://?[^/]+/[^/]+/[^/]+/[^@]+(?:@[^/]+)?)|(?:[^/]+))'

# Keep settings, use different ROOT_URLCONF
ROOT_URLCONF = 'test_urls'
