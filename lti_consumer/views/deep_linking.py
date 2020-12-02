"""
LTI Advantage Deep Linking views.
"""
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_http_methods

from opaque_keys.edx.keys import UsageKey

from lti_consumer.exceptions import LtiError
from lti_consumer.models import LtiConfiguration, LtiDlContentItem


@login_required
@xframe_options_sameorigin
@require_http_methods(["GET"])
def deep_linking_content_presentation(request, usage_id=None):
    """
    LTI Advantage Deep Linking content presentation endpoint.

    This checks if the user is authenticated and has access
    to the LTI integration being launched.

    If access is granted,nproceed with the content presentation.
    If access is denied, throw error 404 to avoid leaking LTI
    block location data.
    """
    usage_key = UsageKey.from_string(usage_id)
    lti_config = get_object_or_404(LtiConfiguration, location=usage_key)

    try:
        # Check user access
        allowed = has_access(request.user, 'load', lti_config.block, usage_key.course_key)
        if not allowed:
            raise LtiError("This user does not have access to this content.")

        # Retrieve content items and throw if none available
        content_items = LtiDlContentItem.objects.filter(lti_configuration=lti_config)
        if not content_items:
            # While this is raising an error here, the user will only see a 404.
            # In normal situations, students will never end up here.
            raise LtiError("No deep linking content available for this resource.")

        # Handle content presentation here.

        return HttpResponse(status=200)

    except LtiError:
        return HttpResponse(status=404)
