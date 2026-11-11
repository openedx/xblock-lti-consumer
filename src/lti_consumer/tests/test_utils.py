"""
Utility functions used within unit tests
"""

import urllib
from unittest.mock import Mock, patch

from Cryptodome.PublicKey import RSA
from django.test.testcases import TestCase
from opaque_keys.edx.keys import CourseKey
from opaque_keys.edx.locator import LocalId
from webob import Request
from workbench.runtime import WorkbenchRuntime
from xblock.fields import ScopeIds
from xblock.runtime import DictKeyValueStore, KvsFieldData

FAKE_USER_ID = 'fake_user_id'


def make_xblock(xblock_name, xblock_cls, attributes):
    """
    Helper to construct XBlock objects
    """
    runtime = WorkbenchRuntime()
    key_store = DictKeyValueStore()
    db_model = KvsFieldData(key_store)
    course_id = 'course-v1:edX+DemoX+Demo_Course'
    course_key = CourseKey.from_string(course_id)
    ids = generate_scope_ids(course_key, xblock_name)

    xblock = xblock_cls(runtime, db_model, scope_ids=ids)
    xblock.category = Mock()

    xblock.runtime = Mock(
        hostname='localhost',
    )
    for key, value in attributes.items():
        setattr(xblock, key, value)
    return xblock


def make_reusable_configuration(generate_keys=True, **kwargs):
    """Create a reusable configuration row for runtime tests.

    Placement runtime reads identity, keys and binding from the reusable table, so a
    bound registration is the fixture for launch and service tests. Keys are generated
    once here, as an API create would, unless a test exercises lazy generation itself.
    """
    from lti_consumer.models import ReusableLtiConfiguration  # pylint: disable=import-outside-toplevel

    values = {
        'name': 'Test reusable configuration',
        'version': ReusableLtiConfiguration.LTI_1P3,
        'context_type': 'site',
        'context_key': '',
        'lti_1p3_client_id': 'test-client-id',
    }
    values.update(kwargs)
    configuration = ReusableLtiConfiguration.objects.create(**values)
    if generate_keys and configuration.version == ReusableLtiConfiguration.LTI_1P3:
        configuration.generate_lti_1p3_keys_if_missing()
        if 'lti_1p3_tool_public_key' not in kwargs and 'lti_1p3_tool_keyset_url' not in kwargs:
            # A valid tool key keeps consumer construction realistic; tests that need a
            # blank or keyset-url source pass it explicitly.
            configuration.lti_1p3_tool_public_key = RSA.import_key(
                configuration.lti_1p3_internal_private_key
            ).publickey().export_key().decode()
            configuration.save()
    return configuration


def generate_scope_ids(course_key, block_type):
    """
    Helper to generate scope IDs for an XBlock
    """
    usage_key = course_key.make_usage_key(block_type, str(LocalId()))
    return ScopeIds('user', block_type, usage_key, usage_key)


def make_request(body, method='POST'):
    """
    Helper to make a request
    """
    request = Request.blank('/')
    request.method = 'POST'
    request.body = body.encode('utf-8')
    request.method = method
    return request


def make_jwt_request(token, **overrides):
    """
    Builds a Request with a JWT body.
    """
    body = {
        "grant_type": "client_credentials",
        "client_assertion_type": "something",
        "client_assertion": token,
        "scope": "",
    }
    request = make_request(urllib.parse.urlencode({**body, **overrides}), 'POST')
    request.content_type = 'application/x-www-form-urlencoded'
    return request


def dummy_processor(_xblock):
    """
    A dummy LTI parameter processor.
    """
    return {
        'custom_author_email': 'author@example.com',
        'custom_author_country': '',
    }


def defaulting_processor(_xblock):
    """
    A dummy LTI parameter processor with default params.
    """


defaulting_processor.lti_xblock_default_params = {
    'custom_name': 'Lex',
    'custom_country': '',
}


def get_mock_lti_configuration(editable):
    """
    Returns a mock object of lti-configuration service

    Arguments:
        editable (bool): This indicates whether the LTI fields (i.e. 'ask_to_send_username', 'ask_to_send_full_name',
        and 'ask_to_send_email') are editable.
    """
    lti_configuration = Mock()
    lti_configuration.configuration = Mock()
    lti_configuration.configuration.lti_access_to_learners_editable = Mock(
        return_value=editable
    )
    return lti_configuration


class TestBaseWithPatch(TestCase):
    """Base test class that mocks xblock imports"""

    def setUp(self):
        """Set up mock patches for xblock imports"""
        self.mock_load_xblock = Mock()
        self.mock_load_xblock.return_value = getattr(self, 'xblock', None)
        self.mock_save_xblock = Mock()
        self.mock_save_xblock.return_value = None

        # Patch the imports
        self.patcher_load = patch('lti_consumer.plugin.compat.load_enough_xblock', self.mock_load_xblock)
        self.patcher_save = patch('lti_consumer.plugin.compat.save_xblock', self.mock_save_xblock)

        self.patcher_load.start()
        self.patcher_save.start()

        super().setUp()

    def tearDown(self):
        """Clean up patches"""
        self.patcher_load.stop()
        self.patcher_save.stop()
        super().tearDown()
