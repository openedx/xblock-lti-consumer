"""
LTI consumer plugin passthrough views
"""
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.http import HttpResponse, JsonResponse
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django_filters.rest_framework import DjangoFilterBackend
from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import UsageKey
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from lti_consumer.exceptions import LtiError
from lti_consumer.models import (
    LtiConfiguration,
    LtiAgsLineItem,
    LtiDlContentItem,
)

from lti_consumer.lti_1p3.exceptions import Lti1p3Exception
from lti_consumer.lti_1p3.extensions.rest_framework.constants import LTI_DL_CONTENT_TYPE_SERIALIZER_MAP
from lti_consumer.lti_1p3.extensions.rest_framework.serializers import (
    LtiAgsLineItemSerializer,
    LtiAgsScoreSerializer,
    LtiAgsResultSerializer,
)
from lti_consumer.lti_1p3.extensions.rest_framework.permissions import LtiAgsPermissions
from lti_consumer.lti_1p3.extensions.rest_framework.authentication import Lti1p3ApiAuthentication
from lti_consumer.lti_1p3.extensions.rest_framework.renderers import (
    LineItemsRenderer,
    LineItemRenderer,
    LineItemScoreRenderer,
    LineItemResultsRenderer
)
from lti_consumer.lti_1p3.extensions.rest_framework.parsers import (
    LineItemParser,
    LineItemScoreParser,
)
from lti_consumer.plugin.compat import (
    run_xblock_handler,
    run_xblock_handler_noauth,
    user_has_staff_access,
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
        lti_config = LtiConfiguration.objects.get(
            location=UsageKey.from_string(usage_id)
        )

        if lti_config.version != lti_config.LTI_1P3:
            raise LtiError(
                "LTI Error: LTI 1.1 blocks do not have a public keyset endpoint."
            )

        # Retrieve block's Public JWK
        # The underlying method will generate a new Private-Public Pair if one does
        # not exist, and retrieve the values.
        response = JsonResponse(lti_config.lti_1p3_public_jwk)
        response['Content-Disposition'] = 'attachment; filename=keyset.json'
        return response
    except (LtiError, InvalidKeyError, ObjectDoesNotExist):
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
        usage_key_str = request.GET.get('login_hint')
        usage_key = UsageKey.from_string(usage_key_str)

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


# Post from external tool that doesn't
# have access to CSRF tokens
@csrf_exempt
# This URL should work inside an iframe
@xframe_options_sameorigin
# Post only, as required by LTI-DL Specification
@require_http_methods(["POST"])
def deep_linking_response_endpoint(request, lti_config_id=None):
    """
    Deep Linking response endpoint where tool can send back
    """
    try:
        # Retrieve LTI configuration
        lti_config = LtiConfiguration.objects.get(id=lti_config_id)

        # First, check if the user has sufficient permissions to
        # save LTI Deep Linking content through the student.auth API.
        course_key = lti_config.location.course_key
        if not user_has_staff_access(request.user, course_key):
            raise PermissionDenied()

        # Get LTI consumer
        lti_consumer = lti_config.get_lti_consumer()

        # Retrieve Deep Linking return message and validate parameters
        content_items = lti_consumer.check_and_decode_deep_linking_token(
            request.POST.get("JWT")
        )

        # On a transaction, clear older DeepLinking selections, then
        # verify and save each content item passed from the tool.
        with transaction.atomic():
            # Erase older deep linking selection
            LtiDlContentItem.objects.filter(lti_configuration=lti_config).delete()

            for content_item in content_items:
                # Retrieve serializer (or throw error)
                serializer_cls = LTI_DL_CONTENT_TYPE_SERIALIZER_MAP[
                    content_item.get('type')
                ]

                # Validate content item data
                serializer = serializer_cls(data=content_item)
                serializer.is_valid(True)

                # Save content item
                LtiDlContentItem.objects.create(
                    lti_configuration=lti_config,
                    content_type=LtiDlContentItem.LTI_RESOURCE_LINK,
                    attributes=serializer.validated_data,
                )

        # TODO: Redirect the user to the launch endpoint, and present content
        # selected in Deep Linking flow. Can only be completed once content
        # presentation is implemented. For now, return ok status page
        return HttpResponse(status=200)

    # If LtiConfiguration doesn't exist, error with 404 status.
    except LtiConfiguration.DoesNotExist:
        return HttpResponse(status=404)
    # Bad JWT message, invalid token, or any message validation issues
    except (Lti1p3Exception, KeyError, PermissionDenied):
        # TODO: Add template with error message
        return HttpResponse(status=403)


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

    @action(
        detail=True,
        methods=['GET'],
        url_path='results/(?P<user_id>[^/.]+)?',
        renderer_classes=[LineItemResultsRenderer]
    )
    def results(self, request, user_id=None, **kwargs):  # pylint: disable=unused-argument
        """
        Return a Result list for an LtiAgsLineItem

        URL Parameters:
          * user_id (string): String external user id representation.

        Query Parameters:
          * limit (integer): The maximum number of records to return. Records are
                sorted with most recent timestamp first

        Returns:
          * An array of Result records, formatted by LtiAgsResultSerializer
                and returned with the media-type for LineItemResultsRenderer
        """
        line_item = self.get_object()
        scores = line_item.scores.filter(score_given__isnull=False).order_by('-timestamp')

        if user_id:
            scores = scores.filter(user_id=user_id)

        if request.query_params.get('limit'):
            scores = scores[:int(request.query_params.get('limit'))]

        serializer = LtiAgsResultSerializer(
            list(scores),
            context={'request': self.request},
            many=True,
        )

        return Response(serializer.data)

    @action(
        detail=True,
        methods=['POST'],
        parser_classes=[LineItemScoreParser],
        renderer_classes=[LineItemScoreRenderer]
    )
    def scores(self, request, *args, **kwargs):  # pylint: disable=unused-argument
        """
        Create a Score record for an LtiAgsLineItem

        Data:
          * A JSON object capable of being serialized by LtiAgsScoreSerializer

        Returns:
          * An copy of the saved record, formatted by LtiAgsScoreSerializer
                and returned with the media-type for LineItemScoreRenderer
        """
        line_item = self.get_object()

        user_id = request.data.get('userId')

        # Using `filter` and `first` so that when a score does not exist,
        # `existing_score` is set to `None`. Using `get` will raise `DoesNotExist`
        existing_score = line_item.scores.filter(user_id=user_id).first()

        serializer = LtiAgsScoreSerializer(
            instance=existing_score,
            data=request.data,
            context={'request': self.request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(line_item=line_item)
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers
        )
