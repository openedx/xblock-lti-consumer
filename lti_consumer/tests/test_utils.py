"""
Utility functions used within unit tests
"""

from unittest.mock import Mock
import urllib

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
