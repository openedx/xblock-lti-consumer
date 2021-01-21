#!/usr/bin/env python
"""
Run tests for the LTI Consumer XBlock
"""

import os
import sys

if __name__ == '__main__':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'test_settings')

    try:
        from django.conf import settings  # pylint: disable=wrong-import-position
        from django.core.management import execute_from_command_line  # pylint: disable=wrong-import-position
    except ImportError:
        # The above import may fail for some other reason. Ensure that the
        # issue is really that Django is missing to avoid masking other
        # exceptions on Python 2.
        try:
            import django  # pylint: disable=unused-import, wrong-import-position
        except ImportError:
            raise ImportError(
                "Couldn't import Django. Are you sure it's installed and "
                "available on your PYTHONPATH environment variable? Did you "
                "forget to activate a virtual environment?"
            )
        raise

    settings.INSTALLED_APPS += ('lti_consumer',)

    arguments = sys.argv[1:]
    options = [argument for argument in arguments if argument.startswith('-')]
    paths = [argument for argument in arguments if argument not in options]
    execute_from_command_line([sys.argv[0], 'test'] + paths + options)
