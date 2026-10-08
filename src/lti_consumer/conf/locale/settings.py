"""
Django settings for xblock-lti-consumer project.

These settings are only used for the purpose of
compiling translations.
"""

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
from __future__ import absolute_import
import os
BASE_DIR = os.path.dirname(os.path.dirname(__file__))


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.11/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
# This is just a container for running tests, it's okay to allow it to be
# defaulted here if not present in environment settings
SECRET_KEY = os.environ.get('SECRET_KEY', '",cB3Jr.?xu[x_Ci]!%HP>#^AVmWi@r/W3u,w?pY+~J!R>;WN+,3}Sb{K=Jp~;&k')

# SECURITY WARNING: don't run with debug turned on in production!
# This is just a container for running tests
DEBUG = True

TEMPLATE_DEBUG = True

ALLOWED_HOSTS = []


# Application definition

INSTALLED_APPS = (
    'statici18n',
    'lti_consumer',
)

# Internationalization
# https://docs.djangoproject.com/en/1.11/topics/i18n/

LANGUAGE_CODE = 'en'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.11/howto/static-files/

STATIC_URL = '/public/'

# statici18n
# http://django-statici18n.readthedocs.io/en/latest/settings.html

LANGUAGES = [
    ('ar', 'Arabic'),
    ('en', 'English - Source Language'),
    ('es_419', 'Spanish (Latin America)'),
    ('fr', 'French'),
    ('he', 'Hebrew'),
    ('hi', 'Hindi'),
    ('it', 'Italian'),
    ('ja', 'Japanese'),
    ('ko', 'Korean (Korea)'),
    ('pt_BR', 'Portuguese (Brazil)'),
    ('pt_PT', 'Portuguese (Portugal)'),
    ('ru', 'Russian'),
    ('zh_CN', 'Chinese (China)'),
]

STATICI18N_DOMAIN = 'text'
STATICI18N_NAMESPACE = 'XBlockLtiConsumerI18N'
STATICI18N_PACKAGES = (
    'lti_consumer',
)
STATICI18N_ROOT = 'lti_consumer/public/js'
STATICI18N_OUTPUT_DIR = 'translations'
