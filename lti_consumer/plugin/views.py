"""
LTI consumer plugin passthrough views
"""

from django.http import HttpResponse

from opaque_keys.edx.keys import UsageKey  # pylint: disable=import-error
from lms.djangoapps.courseware.module_render import (  # pylint: disable=import-error
    handle_xblock_callback,
    handle_xblock_callback_noauth,
)


def public_keyset_endpoint(request, usage_id=None):
    """
    Gate endpoint to fetch public keysets from a problem

    This is basically a passthrough function that uses the
    OIDC response parameter `login_hint` to locate the block
    and run the proper handler.
    """
    try:
        usage_key = UsageKey.from_string(usage_id)

        return handle_xblock_callback_noauth(
            request=request,
            course_id=str(usage_key.course_key),
            usage_id=str(usage_key),
            handler='public_keyset_endpoint'
        )
    except:  # pylint: disable=bare-except
        return HttpResponse(status=404)


def launch_gate_endpoint(request, suffix):
    """
    Gate endpoint that triggers LTI launch endpoint XBlock handler

    This is basically a passthrough function that uses the
    OIDC response parameter `login_hint` to locate the block
    and run the proper handler.
    """
    try:
        usage_key = UsageKey.from_string(
            request.GET.get('login_hint')
        )

        return handle_xblock_callback(
            request=request,
            course_id=str(usage_key.course_key),
            usage_id=str(usage_key),
            handler='lti_1p3_launch_callback',
            suffix=suffix
        )
    except:  # pylint: disable=bare-except
        return HttpResponse(status=404)
