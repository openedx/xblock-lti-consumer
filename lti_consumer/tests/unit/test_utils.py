"""
Utility functions used within unit tests
"""

from mock import Mock
from webob import Request
from workbench.runtime import WorkbenchRuntime
from xblock.fields import ScopeIds
from xblock.runtime import DictKeyValueStore, KvsFieldData

FAKE_USER_ID = 'fake_user_id'


def make_xblock(xblock_name, xblock_cls, attributes, is_past_due_patch=None):
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

    # mock is_past_due method
    if is_past_due_patch:
        xblock.is_past_due = is_past_due_patch

    xblock.course_id = 'course-v1:edX+DemoX+Demo_Course'
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
