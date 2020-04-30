# -*- coding: utf-8 -*-
"""
lti_consumer Django application initialization.
"""
from __future__ import absolute_import, unicode_literals

from django.apps import AppConfig


class LTIConsumerApp(AppConfig):
    """
    Configuration for the lti_consumer Django application.
    """

    name = 'lti_consumer'

    # Set LMS urls for LTI endpoints
    # Urls are under /api/lti_consumer/
    plugin_app = {
        'url_config': {
            'lms.djangoapp': {
                'namespace': 'lti_consumer',
                'regex': '^api/',
                'relative_path': 'plugin.urls',
            }
        }
    }
