"""
Utility functions used within unit tests
"""

from webob import Request
from mock import Mock

from xblock.fields import ScopeIds
from xblock.runtime import KvsFieldData, DictKeyValueStore

from workbench.runtime import WorkbenchRuntime


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
    xblock.course_id = 'course-v1:edX+DemoX+Demo_Course'
    for key, value in attributes.iteritems():
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
