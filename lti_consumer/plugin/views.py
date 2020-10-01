"""
LTI consumer plugin passthrough views
"""
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_filters.rest_framework import DjangoFilterBackend
from opaque_keys.edx.keys import UsageKey
from rest_framework import viewsets

from lti_consumer.models import LtiAgsLineItem
from lti_consumer.lti_1p3.extensions.rest_framework.serializers import LtiAgsLineItemSerializer
from lti_consumer.lti_1p3.extensions.rest_framework.permissions import LtiAgsPermissions
from lti_consumer.lti_1p3.extensions.rest_framework.authentication import Lti1p3ApiAuthentication
from lti_consumer.lti_1p3.extensions.rest_framework.renderers import LineItemsRenderer, LineItemRenderer
from lti_consumer.lti_1p3.extensions.rest_framework.parsers import LineItemParser
from lti_consumer.plugin.compat import (
    run_xblock_handler,
    run_xblock_handler_noauth,
)


@require_http_methods(["GET"])
def public_keyset_endpoint(request, usage_id=None):
    """
    Gate endpoint to fetch public keysets from a problem

    This is basically a passthrough function that uses the
    OIDC response parameter `login_hint` to locate the block
    and run the proper handler.
    """
    try:
        usage_key = UsageKey.from_string(usage_id)

        return run_xblock_handler_noauth(
            request=request,
            course_id=str(usage_key.course_key),
            usage_id=str(usage_key),
            handler='public_keyset_endpoint'
        )
    except Exception:  # pylint: disable=broad-except
        return HttpResponse(status=404)


@require_http_methods(["GET", "POST"])
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

        return run_xblock_handler(
            request=request,
            course_id=str(usage_key.course_key),
            usage_id=str(usage_key),
            handler='lti_1p3_launch_callback',
            suffix=suffix
        )
    except Exception:  # pylint: disable=broad-except
        return HttpResponse(status=404)


@csrf_exempt
@require_http_methods(["POST"])
def access_token_endpoint(request, usage_id=None):
    """
    Gate endpoint to enable tools to retrieve access tokens
    """
    try:
        usage_key = UsageKey.from_string(usage_id)

        return run_xblock_handler_noauth(
            request=request,
            course_id=str(usage_key.course_key),
            usage_id=str(usage_key),
            handler='lti_1p3_access_token'
        )
    except Exception:  # pylint: disable=broad-except
        return HttpResponse(status=404)


class LtiAgsLineItemViewset(viewsets.ModelViewSet):
    """
    LineItem endpoint implementation from LTI Advantage.

    See full documentation at:
    https://www.imsglobal.org/spec/lti-ags/v2p0#line-item-service
    """
    serializer_class = LtiAgsLineItemSerializer
    pagination_class = None

    # Custom permission classes for LTI APIs
    authentication_classes = [Lti1p3ApiAuthentication]
    permission_classes = [LtiAgsPermissions]

    # Renderer/parser classes to accept LTI AGS content types
    renderer_classes = [
        LineItemsRenderer,
        LineItemRenderer,
    ]
    parser_classes = [LineItemParser]

    # Filters
    filter_backends = [DjangoFilterBackend]
    filterset_fields = [
        'resource_link_id',
        'resource_id',
        'tag'
    ]

    def get_queryset(self):
        lti_configuration = self.request.lti_configuration

        # Return all LineItems related to the LTI configuration.
        # TODO:
        # Note that each configuration currently maps 1:1
        # to each resource link (block), and this filter needs
        # improved once we start reusing LTI configurations.
        return LtiAgsLineItem.objects.filter(
            lti_configuration=lti_configuration
        )

    def perform_create(self, serializer):
        lti_configuration = self.request.lti_configuration
        serializer.save(lti_configuration=lti_configuration)
