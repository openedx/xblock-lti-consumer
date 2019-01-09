"""
Utility functions used within unit tests
"""

from webob import Request
from mock import patch, Mock, PropertyMock

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


def patch_signed_parameters(func):
    """
    Prepare the patches for the get_signed_lti_parameters function for tests.
    """
    func = patch(
        'lti_consumer.lti.get_oauth_request_signature',
        Mock(return_value=(
            'OAuth oauth_nonce="fake_nonce", '
            'oauth_timestamp="fake_timestamp", oauth_version="fake_version", oauth_signature_method="fake_method", '
            'oauth_consumer_key="fake_consumer_key", oauth_signature="fake_signature"'
        ))
    )(func)

    func = patch(
        'lti_consumer.lti_consumer.LtiConsumerXBlock.prefixed_custom_parameters',
        PropertyMock(return_value={u'custom_param_1': 'custom1', u'custom_param_2': 'custom2'})
    )(func)

    func = patch(
        'lti_consumer.lti_consumer.LtiConsumerXBlock.lti_provider_key_secret',
        PropertyMock(return_value=('t', 's'))
    )(func)

    func = patch(
        'lti_consumer.lti_consumer.LtiConsumerXBlock.user_id', PropertyMock(return_value=FAKE_USER_ID)
    )(func)

    return func


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
    pass


defaulting_processor.lti_xblock_default_params = {
    'custom_name': 'Lex',
    'custom_country': '',
}


def faulty_processor(_xblock):
    """
    A dummy LTI parameter processor with default params that throws an error.
    """
    raise Exception()


faulty_processor.lti_xblock_default_params = {
    'custom_name': 'Lex',
}
