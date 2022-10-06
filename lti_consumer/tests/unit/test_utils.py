"""
Utility functions used within unit tests
"""

from unittest.mock import Mock
import urllib
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
    ids = generate_scope_ids(runtime, xblock_name)
    xblock = xblock_cls(runtime, db_model, scope_ids=ids)
    xblock.category = Mock()
    xblock.location = Mock(
        html_id=Mock(return_value='sample_element_id'),
    )
    xblock.runtime = Mock(
        hostname='localhost',
    )
    xblock.runtime.scope_ids.usage_id.context_key = 'course-v1:edX+DemoX+Demo_Course'
    for key, value in attributes.items():
        setattr(xblock, key, value)
    return xblock


def generate_scope_ids(runtime, block_type):
    """
    Helper to generate scope IDs for an XBlock
    """
    def_id = runtime.id_generator.create_definition(block_type)
    usage_id = runtime.id_generator.create_usage(def_id)
    return ScopeIds('user', block_type, def_id, usage_id)


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
