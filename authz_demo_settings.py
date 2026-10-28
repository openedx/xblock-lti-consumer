"""
Settings for trying reusable LTI configuration permissions by hand.

    python manage.py migrate --run-syncdb --settings=authz_demo_settings  # stub models have no migrations
    python manage.py seed_lti_authz_demo --settings=authz_demo_settings
    python manage.py runserver --settings=authz_demo_settings
"""
from test_settings import *  # pylint: disable=wildcard-import,unused-wildcard-import

# test.py adds lti_consumer at runtime for the test suite; rest_framework
# provides the browsable API's login page and templates.
INSTALLED_APPS += ["lti_consumer", "rest_framework"]

# With DEBUG on, workbench's catch-all static URL swallows the API routes.
DEBUG = False

# test_settings sets PAGE_SIZE for its pagination tests; harmless here.
SILENCED_SYSTEM_CHECKS = ["rest_framework.W001"]
