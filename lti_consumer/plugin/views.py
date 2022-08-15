"""
LTI consumer plugin passthrough views
"""
import logging
import urllib

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.http import JsonResponse, Http404
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.shortcuts import redirect, render
from django.utils.crypto import get_random_string
from django_filters.rest_framework import DjangoFilterBackend
from edx_django_utils.cache import get_cache_key, TieredCache
from jwkest.jwt import JWT, BadSyntax
from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import UsageKey
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.status import HTTP_400_BAD_REQUEST, HTTP_403_FORBIDDEN, HTTP_404_NOT_FOUND

from lti_consumer.api import get_lti_pii_sharing_state_for_course, get_lti_1p3_launch_start_url
from lti_consumer.exceptions import LtiError
from lti_consumer.models import (
    LtiConfiguration,
    LtiAgsLineItem,
    LtiDlContentItem,
)

from lti_consumer.lti_1p3.consumer import LTI_1P3_CONTEXT_TYPE
from lti_consumer.lti_1p3.exceptions import (
    BadJwtSignature,
    Lti1p3Exception,
    LtiDeepLinkingContentTypeNotSupported,
    UnsupportedGrantType,
    MalformedJwtToken,
    MissingRequiredClaim,
    NoSuitableKeys,
    TokenSignatureExpired,
    UnknownClientId,
)
from lti_consumer.lti_1p3.extensions.rest_framework.constants import LTI_DL_CONTENT_TYPE_SERIALIZER_MAP
from lti_consumer.lti_1p3.extensions.rest_framework.serializers import (
    LtiAgsLineItemSerializer,
    LtiAgsScoreSerializer,
    LtiAgsResultSerializer,
    LtiNrpsContextMembershipBasicSerializer,
    LtiNrpsContextMembershipPIISerializer,
)
from lti_consumer.lti_1p3.extensions.rest_framework.permissions import (
    LtiAgsPermissions,
    LtiNrpsContextMembershipsPermissions,
)
from lti_consumer.lti_1p3.extensions.rest_framework.authentication import Lti1p3ApiAuthentication
from lti_consumer.lti_1p3.extensions.rest_framework.renderers import (
    LineItemsRenderer,
    LineItemRenderer,
    LineItemScoreRenderer,
    LineItemResultsRenderer,
    MembershipResultRenderer,
)
from lti_consumer.lti_1p3.extensions.rest_framework.parsers import (
    LineItemParser,
    LineItemScoreParser,
)
from lti_consumer.lti_1p3.extensions.rest_framework.utils import IgnoreContentNegotiation
from lti_consumer.plugin import compat
from lti_consumer.utils import _
from lti_consumer.track import track_event


log = logging.getLogger(__name__)


def has_block_access(user, block, course_key):
    """
    Checks if a user has access to given xblock.

    ``has_access`` doesn't checks for course enrollment. On the otherhand, ``get_course_with_access``
    only checks for the course itself. There is no way to check access for specific xblock. This function
    has been created to perform a combination of check for both enrollment and access for specific xblock.

    Args:
        user: User Object
        block: xblock Object to check permission for
        course_key: A course_key specifying which course run this access is for.

    Returns:
        bool: True if user has access, False otherwise.
    """
    # Get the course
    course = compat.get_course_by_id(course_key)

    # Check if user is authenticated & enrolled
    course_access = compat.user_course_access(course, user, 'load', check_if_enrolled=True, check_if_authenticated=True)

    # Check if user has access to xblock
    block_access = compat.user_has_access(user, 'load', block, course_key)

    # Return True if the user has access to xblock and is enrolled in that specific course.
    return course_access and block_access


@require_http_methods(["GET"])
def public_keyset_endpoint(request, usage_id=None, lti_config_id=None):
    """
    Gate endpoint to fetch public keysets from a problem

    This is basically a passthrough function that uses the
    OIDC response parameter `login_hint` to locate the block
    and run the proper handler.
    """
    try:
        if usage_id:
            lti_config = LtiConfiguration.objects.get(location=UsageKey.from_string(usage_id))
        elif lti_config_id:
            lti_config = LtiConfiguration.objects.get(config_id=lti_config_id)

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
    except (LtiError, InvalidKeyError, ObjectDoesNotExist) as exc:
        log.info(
            "Error while retrieving keyset for usage_id (%r) or lit_config_id (%s): %s",
            usage_id,
            lti_config_id,
            exc,
            exc_info=True,
        )
        raise Http404 from exc


@require_http_methods(["GET", "POST"])
def launch_gate_endpoint(request, suffix=None):  # pylint: disable=unused-argument
    """
    Gate endpoint that triggers LTI launch endpoint XBlock handler

    This uses the location key from the "login_hint" query parameter
    to identify the LtiConfiguration and its consumer to generate the
    LTI 1.3 Launch Form.
    """
    usage_id = request.GET.get('login_hint')
    if not usage_id:
        log.info('The `login_hint` query param in the request is missing or empty.')
        return render(request, 'html/lti_1p3_launch_error.html', status=HTTP_400_BAD_REQUEST)

    try:
        usage_key = UsageKey.from_string(usage_id)
    except InvalidKeyError as exc:
        log.error(
            "The login_hint: %s is not a valid block location. Error: %s",
            usage_id,
            exc,
            exc_info=True
        )
        return render(request, 'html/lti_1p3_launch_error.html', status=HTTP_404_NOT_FOUND)

    try:
        lti_config = LtiConfiguration.objects.get(
            location=usage_key
        )
    except LtiConfiguration.DoesNotExist as exc:
        log.error("Invalid usage_id '%s' for LTI 1.3 Launch callback", usage_id)
        raise Http404 from exc

    if lti_config.version != LtiConfiguration.LTI_1P3:
        log.error("The LTI Version of configuration %s is not LTI 1.3", lti_config)
        return render(request, 'html/lti_1p3_launch_error.html', status=HTTP_404_NOT_FOUND)

    context = {}

    course_key = usage_key.course_key
    course = compat.get_course_by_id(course_key)
    user_role = compat.get_user_role(request.user, course_key)
    external_user_id = compat.get_external_id_for_user(request.user)
    lti_consumer = lti_config.get_lti_consumer()

    try:
        # Pass user data
        # Pass django user role to library
        lti_consumer.set_user_data(user_id=external_user_id, role=user_role)

        # Set launch context
        # Hardcoded for now, but we need to translate from
        # self.launch_target to one of the LTI compliant names,
        # either `iframe`, `frame` or `window`
        # This is optional though
        lti_consumer.set_launch_presentation_claim('iframe')

        # Set context claim
        # This is optional
        context_title = " - ".join([
            course.display_name_with_default,
            course.display_org_with_default
        ])
        # Course ID is the context ID for the LTI for now. This can be changed to be
        # more specific in the future for supporting other tools like discussions, etc.
        lti_consumer.set_context_claim(
            str(course_key),
            context_types=[LTI_1P3_CONTEXT_TYPE.course_offering],
            context_title=context_title,
            context_label=str(course_key)
        )

        # Retrieve preflight response
        preflight_response = request.GET.dict()
        lti_message_hint = preflight_response.get('lti_message_hint', '')

        # Set LTI Launch URL
        context.update({'launch_url': lti_consumer.launch_url})

        # Modify LTI Launch URL dependind on launch type
        # Deep Linking Launch - Configuration flow launched by
        # course creators to set up content.
        if lti_consumer.dl and lti_message_hint == 'deep_linking_launch':
            # Check if the user is staff before LTI doing deep linking launch.
            # If not, raise exception and display error page
            if user_role not in ['instructor', 'staff']:
                raise AssertionError('Deep Linking can only be performed by instructors and staff.')
            # Set deep linking launch
            context.update({'launch_url': lti_consumer.dl.deep_linking_launch_url})

        # Deep Linking ltiResourceLink content presentation
        # When content type is `ltiResourceLink`, the tool will be launched with
        # different parameters, set by instructors when running the DL configuration flow.
        elif lti_consumer.dl and 'deep_linking_content_launch' in lti_message_hint:
            # Retrieve Deep Linking parameters using lti_message_hint parameter.
            deep_linking_id = lti_message_hint.split(':')[1]
            content_item = lti_config.ltidlcontentitem_set.get(pk=deep_linking_id)
            # Only filter DL content item from content item set in the same LTI configuration.
            # This avoids a malicious user to input a random LTI id and perform LTI DL
            # content launches outside the scope of its configuration.
            dl_params = content_item.attributes

            # Modify LTI launch and set ltiResourceLink parameters
            lti_consumer.set_dl_content_launch_parameters(
                url=dl_params.get('url'),
                custom=dl_params.get('custom')
            )

        # Update context with LTI launch parameters
        context.update({
            "preflight_response": preflight_response,
            "launch_request": lti_consumer.generate_launch_request(
                resource_link=usage_id,
                preflight_response=preflight_response
            )
        })
        event = {
            'lti_version': lti_config.version,
            'user_roles': user_role,
            'launch_url': context['launch_url']
        }
        track_event('xblock.launch_request', event)

        return render(request, 'html/lti_1p3_launch.html', context)
    except Lti1p3Exception as exc:
        log.warning(
            "Error preparing LTI 1.3 launch for block %r: %s",
            usage_id,
            exc,
            exc_info=True
        )
        return render(request, 'html/lti_1p3_launch_error.html', context, status=HTTP_400_BAD_REQUEST)
    except AssertionError as exc:
        log.warning(
            "Permission on LTI block %r denied for user %r: %s",
            usage_id,
            external_user_id,
            exc,
            exc_info=True
        )
        return render(request, 'html/lti_1p3_permission_error.html', context, status=HTTP_403_FORBIDDEN)


@csrf_exempt
@require_http_methods(["POST"])
def access_token_endpoint(request, lti_config_id=None, usage_id=None):
    """
    Gate endpoint to enable tools to retrieve access tokens for the LTI 1.3 tool.

    This endpoint is only valid when a LTI 1.3 tool is being used.

    Arguments:
        lti_config_id (UUID): config_id of the LtiConfiguration
        usage_id (UsageKey): location of the Block

    Returns:
        JsonResponse or Http404

    References:
        Sucess: https://tools.ietf.org/html/rfc6749#section-4.4.3
        Failure: https://tools.ietf.org/html/rfc6749#section-5.2
    """

    try:
        if lti_config_id:
            lti_config = LtiConfiguration.objects.get(config_id=lti_config_id)
        else:
            usage_key = UsageKey.from_string(usage_id)
            lti_config = LtiConfiguration.objects.get(location=usage_key)
    except LtiConfiguration.DoesNotExist as exc:
        log.warning("Error getting the LTI configuration with id %r: %s", lti_config_id, exc, exc_info=True)
        raise Http404 from exc

    if lti_config.version != lti_config.LTI_1P3:
        return JsonResponse({"error": "invalid_lti_version"}, status=HTTP_404_NOT_FOUND)

    lti_consumer = lti_config.get_lti_consumer()
    try:
        token = lti_consumer.access_token(
            dict(urllib.parse.parse_qsl(
                request.body.decode('utf-8'),
                keep_blank_values=True
            ))
        )
        return JsonResponse(token)

    # Handle errors and return a proper response
    except MissingRequiredClaim:
        # Missing request attibutes
        return JsonResponse({"error": "invalid_request"}, status=HTTP_400_BAD_REQUEST)
    except (MalformedJwtToken, TokenSignatureExpired):
        # Triggered when a invalid grant token is used
        return JsonResponse({"error": "invalid_grant"}, status=HTTP_400_BAD_REQUEST)
    except (NoSuitableKeys, UnknownClientId):
        # Client ID is not registered in the block or
        # isn't possible to validate token using available keys.
        return JsonResponse({"error": "invalid_client"}, status=HTTP_400_BAD_REQUEST)
    except UnsupportedGrantType:
        return JsonResponse({"error": "unsupported_grant_type"}, status=HTTP_400_BAD_REQUEST)

# Post from external tool that doesn't
# have access to CSRF tokens
@csrf_exempt
# This URL should work inside an iframe
@xframe_options_sameorigin
# Post only, as required by LTI-DL Specification
@require_http_methods(["POST"])
def deep_linking_response_endpoint(request, lti_config_id=None):
    """
    Deep Linking response endpoint where tool can send back Deep Linking
    content selected by instructions in the tool's UI.

    For this feature to work, the LMS session cookies need to be Secure
    and have the `SameSite` attribute set to `None`, otherwise we won't
    be able to check user permissions.
    """
    try:
        # Retrieve LTI configuration
        lti_config = LtiConfiguration.objects.get(id=lti_config_id)

        # Get LTI consumer
        lti_consumer = lti_config.get_lti_consumer()

        # Validate Deep Linking return message and return decoded message
        content_items = lti_consumer.check_and_decode_deep_linking_token(
            request.POST.get("JWT")
        )

        # Check if the user has sufficient permissions to
        # save LTI Deep Linking content through the student.auth API.
        course_key = lti_config.location.course_key
        if not compat.user_has_studio_write_access(request.user, course_key):
            raise PermissionDenied()

        # On a transaction, clear older DeepLinking selections, then
        # verify and save each content item passed from the tool.
        with transaction.atomic():
            # Erase older deep linking selection
            LtiDlContentItem.objects.filter(lti_configuration=lti_config).delete()

            for content_item in content_items:
                content_type = content_item.get('type')

                # Retrieve serializer (or raise)
                # pylint: disable=consider-iterating-dictionary
                if content_type not in LTI_DL_CONTENT_TYPE_SERIALIZER_MAP.keys():
                    raise LtiDeepLinkingContentTypeNotSupported()
                serializer_cls = LTI_DL_CONTENT_TYPE_SERIALIZER_MAP[content_type]

                # Validate content item data
                serializer = serializer_cls(data=content_item)
                serializer.is_valid(True)

                # Save content item
                LtiDlContentItem.objects.create(
                    lti_configuration=lti_config,
                    content_type=content_type,
                    attributes=serializer.validated_data,
                )

        # Display sucess page to indicate that LTI DL Content was
        # saved successfully and auto-close after a few seconds.
        return render(request, 'html/lti-dl/dl_response_saved.html')

    # If LtiConfiguration doesn't exist, error with 404 status.
    except LtiConfiguration.DoesNotExist as exc:
        log.info("LtiConfiguration %r does not exist: %s", lti_config_id, exc)
        raise Http404 from exc
    # If the deep linking content type is not supported
    except LtiDeepLinkingContentTypeNotSupported as exc:
        log.info("One of the selected LTI Content Types is not supported: %s", exc)
        return render(
            request,
            'html/lti-dl/dl_response_error.html',
            {"error": _("The selected content type is not supported by Open edX.")},
            status=400
        )
    # Bad JWT message, invalid token, or any other message validation issues
    except (Lti1p3Exception, PermissionDenied) as exc:
        log.warning(
            "Permission on LTI Config %r denied for user %r: %s",
            lti_config,
            request.user,
            exc,
        )
        return render(
            request,
            'html/lti-dl/dl_response_error.html',
            {
                "error": _("You don't have access to save LTI Content Items."),
                "explanation": _("Please check that you have course staff permissions "
                                 "and double check this block's LTI settings."),
            },
            status=403
        )


@require_http_methods(['GET'])
@xframe_options_sameorigin
def deep_linking_content_endpoint(request, lti_config_id=None):
    """
    Deep Linking endpoint for rendering Deep Linking Content Items.
    """
    try:
        # Get LTI Configuration
        lti_config = LtiConfiguration.objects.get(id=lti_config_id)
    except LtiConfiguration.DoesNotExist as exc:
        log.info("LtiConfiguration %r does not exist: %s", lti_config_id, exc)
        raise Http404 from exc

    # check if user has proper access
    if not has_block_access(request.user, lti_config.block, lti_config.location.course_key):
        log.warning(
            "Permission on LTI Config %r denied for user %r.",
            lti_config_id,
            request.user,
        )
        raise PermissionDenied

    # Get all LTI-DL contents
    content_items = LtiDlContentItem.objects.filter(lti_configuration=lti_config)

    # If no LTI-DL contents found for current configuration, throw 404 error
    if not content_items.exists():
        log.info("There's no Deep linking content for LTI configuration %s.", lti_config)
        raise Http404

    # Render LTI-DL contents
    return render(request, 'html/lti-dl/render_dl_content.html', {
        'content_items': content_items,
        'block': lti_config.block,
    })


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
        renderer_classes=[LineItemResultsRenderer],
        content_negotiation_class=IgnoreContentNegotiation,
    )
    def results(self, request, user_id=None, **kwargs):
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
        renderer_classes=[LineItemScoreRenderer],
        content_negotiation_class=IgnoreContentNegotiation,
    )
    def scores(self, request, *args, **kwargs):
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


class LtiNrpsContextMembershipViewSet(viewsets.ReadOnlyModelViewSet):
    """
    LTI NRPS Context Membership Service endpoint.

    See full documentation at:
    http://imsglobal.org/spec/lti-nrps/v2p0
    """

    # Custom permission classes for LTI APIs
    authentication_classes = [Lti1p3ApiAuthentication]
    permission_classes = [LtiNrpsContextMembershipsPermissions]

    # Renderer classes to accept LTI NRPS content types
    renderer_classes = [
        MembershipResultRenderer,
    ]

    def attach_external_user_ids(self, data):
        """
        Preprocess the output of `get_membership` method amd appends external ids to each user.
        """

        # batch get or create external ids for all users
        user_ids = data.keys()
        users = get_user_model().objects.prefetch_related('profile').filter(id__in=user_ids)

        # get external ids
        external_ids = compat.batch_get_or_create_externalids(users)

        for userid in user_ids:
            # append external ids to user
            data[userid]['external_id'] = external_ids[userid].external_user_id

    def get_serializer_class(self):
        """
        Overrides ModelViewSet's `get_serializer_class` method.
        Checks if PII fields can be exposed and returns appropiate serializer.
        """
        if get_lti_pii_sharing_state_for_course(self.request.lti_configuration.location.course_key):
            return LtiNrpsContextMembershipPIISerializer
        else:
            return LtiNrpsContextMembershipBasicSerializer

    def list(self, *args, **kwargs):
        """
        Overrides default list method of ModelViewSet. Calls LMS `get_course_members`
        API and returns result.
        """

        # get course key
        course_key = self.request.lti_configuration.location.course_key

        try:
            data = compat.get_course_members(course_key)
            self.attach_external_user_ids(data)

            # build correct format for the serializer
            result = {
                'id': self.request.build_absolute_uri(),
                'context': {
                    'id': course_key
                },
                'members': data.values(),
            }

            # Serialize and return data NRPS reponse.
            serializer = self.get_serializer_class()(result)
            return Response(serializer.data)

        except LtiError as ex:
            log.warning("LTI NRPS Error: %s", ex)
            return Response({
                "error": "above_response_limit",
                "explanation": "The number of retrieved users is bigger than the maximum allowed in the configuration.",
            }, status=HTTP_403_FORBIDDEN)


def proctoring_preflight(request, lti_config_id):
    """
    This view represents a "Platform-Originating Message"; the Assessment Platform is directing the browser to send a
     message to the Proctoring Tool. Because the Assessment Platform acts as the identity provider
    (IdP), it must follow the "OpenID Connect Launch Flow". The first step is the third-party initiated login; it is a
    "third-party" initiated login to protect against login CSRF attacks. This is also known as a preflight request.

    "In 3rd party initiated login, the login flow is initiated by an OpenID Provider or another party, rather than the
    Relying Party. In this case, the initiator redirects to the Relying Party at its login initiation endpoint, which
    requests that the Relying Party send an Authentication Request to a specified OpenID Provider."
    https://www.imsglobal.org/spec/security/v1p0/#openid_connect_launch_flow

    This view redirects the user's browser to the Proctoring Tool's initial "OIDC login initiation URL", which acts
    as the first step of third-party initiated login. The Proctoring Tool should redirect the user's browser to the
    Assessment Platform's "OIDC Authorization end-point", which starts the OpenID Connect authentication flow,
    implemented by the launch_gate_endpoint_proctoring view.

    The Assessment Platform needs to know the Proctoring Tool's OIDC login initiation URL. The Proctoring Tool needs to
    know the Assessment Platform's OIDC authorization URL. This information is exchanged out-of-band during the
    registration phase.
    """
    # DECISION: It doesn't appear that the OIDC login initiation/preflight view has been pulled out of the XBlock yet,
    #           so I cannot leverage an existing view. I think uncoupling the view from the XBlock is beyond the scope
    #           of this ticket, so I've written a proctoring specific view here for now.

    try:
        lti_config = LtiConfiguration.objects.get(config_id=lti_config_id)
    except LtiConfiguration.DoesNotExist as exc:
        log.error("The config_id %s is invalid for the LTI 1.3 proctoring launch preflight request.", lti_config_id)
        raise Http404 from exc

    if not lti_config.lti_1p3_proctoring_enabled:
        log.info("Proctoring Services for LTIConfiguration with config_id %s are not enabled", lti_config_id)
        return render(request, 'html/lti_1p3_launch_error.html', status=HTTP_400_BAD_REQUEST)

    # NOTE: The lti_hint could easily be a parameter to this view, which would eliminate the need for the query
    #       parameter. I'd like some feedback about whether this function should be a utility view that is only ever
    #       called by start_proctoring or end_assessment or whether it should be exposed by the library for use by
    #       consumers of the library.
    lti_hint = request.GET.get("lti_hint")
    if not lti_hint:
        log.info("The `lti_hint` query param in the request is missing or empty.")
        return render(request, 'html/lti_1p3_launch_error.html', status=HTTP_400_BAD_REQUEST)
    elif lti_hint not in ["LtiStartProctoring", "LtiEndAssessment"]:
        log.info("The `lti_hint` query param in the request is invalid.")
        return render(request, 'html/lti_1p3_launch_error.html', status=HTTP_400_BAD_REQUEST)

    preflight_url = get_lti_1p3_launch_start_url(
        config_id=lti_config.id,
        lti_hint=lti_hint,
        hint=lti_config_id,
    )

    return redirect(preflight_url)


@require_http_methods(['GET'])
def start_proctoring(request, lti_config_id):
    """
    This view represents a "Platform-Originating Message"; the Assessment Platform is directing the browser to send a
    "start proctoring" message to the Proctoring Tool. Because the Assessment Platform acts as the identity provider
    (IdP), it must follow the "OpenID Connect Launch Flow". The first step is the third-party initiated login; it is a
    "third-party" initiated login to protect against login CSRF attacks. This is also known as a preflight request.
    """
    # Set the lti_hint query parameter appropriately. QueryDicts are immutable, so we must copy the QueryDict
    # and set the query parameter.
    get_params = request.GET.copy()
    get_params['lti_hint'] = 'LtiStartProctoring'
    request.GET = get_params

    return proctoring_preflight(request, lti_config_id)


@require_http_methods(['GET'])
def end_assessment(request, lti_config_id):
    """
    This view represents a "Platform-Originating Message"; the Assessment Platform is directing the browser to send a
    "end assessment" message to the Proctoring Tool. Because the Assessment Platform acts as the identity provider
    (IdP), it must follow the "OpenID Connect Launch Flow". The first step is the third-party initiated login; it is a
    "third-party" initiated login to protect against login CSRF attacks. This is also known as a preflight request.

    The End Assessment message covers the last part of the overall assessment submission workflow. This message
    MUST be sent by the Assessment Platform upon attempt completion IF the end_assessment_return claim is set to True
    by the Proctoring Tool as part of the Start Assessment launch.
    """
    end_assessment_return_key = get_cache_key(app="lti", key="end_assessment_return", user_id=request.user.id)
    cached_end_assessment_return = TieredCache.get_cached_response(end_assessment_return_key)

    # If end_assessment_return was provided by the Proctoring Tool, and end_assessment was True, then the Assessment
    # Platform MUST send an End Assessment message to the Proctoring Tool. Otherwise, the Assessment Platform can
    # complete its normal post-assessment flow.
    if cached_end_assessment_return.is_found and cached_end_assessment_return:
        # Clear the cached end_assessment_return value.
        TieredCache.delete_all_tiers(end_assessment_return_key)

        # Set the lti_message_hint query parameter appropriately. QueryDicts are immutable, so we must copy the
        # QueryDict and set the query parameter.
        get_params = request.GET.copy()
        get_params['lti_hint'] = 'LtiEndAssessment'
        request.GET = get_params

        return proctoring_preflight(request, lti_config_id)
    else:
        return JsonResponse(data={})


# We do not want Django's CSRF protection enabled for POSTs made by external services to this endpoint.
# Please see the comment for the launch_gate_endpoint_proctoring view for a more detailed justification.
@csrf_exempt
# Per the Proctoring Services specification, the Proctoring Tool can direct the user's browser to make only a POST
# request to this endpoint.
@require_http_methods(['POST'])
def start_assessment(request):
    """
    This view handles the Proctoring Tool's message to start the assessment, which is a "Tool-Originating Message".

    Once the Proctoring Tool determines the user is ready to start the proctored assessment (e.g. their environment
    has been secured and they have completed user identity verification), it sends the Assessment Platform an LTI
    message. Because it is a "Tool-Originating Message" and no user identity is shared, the message is a signed JWT, not
    an ID Token.

    The Proctoring Tool needs to know the location of this endpoint on the Assessment Platform; this endpoint is
    referred to as the "start assessment URL". This information is sent to the Proctoring Tool in the Assessment
    Platform's response to the Tool's request to the login endpoint (launch_gate_endpoint_proctoring). It is included as
    the required claim "start_assessment_url" in the ID Token.
    """
    # DECISION: Instead of relying on a config_id URL parameter, let's use the iss claim in signed JWT sent by the
    #           Proctoring Tool to identify the LtiConfiguration; iss should match the client_id of the
    #           LtiConfiguration. Although there is a risk that the JWT is not authentic, we will validate the
    #           authenticity of the JWT and raise an exception if the signature is invalid later in this function.
    token = request.POST.get('JWT')

    # TODO: This needs better error handling.
    try:
        jwt = JWT().unpack(token)
    except BadSyntax:
        return JsonResponse(
            {},
            status=HTTP_400_BAD_REQUEST,
        )

    client_id = jwt.payload().get('iss')

    try:
        lti_config = LtiConfiguration.objects.get(lti_1p3_client_id=client_id)
    except LtiConfiguration.DoesNotExist as exc:
        log.error("The iss claim %s is not valid for the LTI 1.3 proctoring start_assessment request.", client_id)
        raise Http404 from exc

    if not lti_config.lti_1p3_proctoring_enabled:
        log.info("Proctoring Services for LTIConfiguration with config_id %s are not enabled", lti_config.config_id)
        return JsonResponse(
            {'error':
                f'Proctoring Services for LTIConfiguration with config_id {lti_config.config_id} are not enabled'},
            status=HTTP_400_BAD_REQUEST,
        )

    lti_consumer = lti_config.get_lti_consumer()

    # Let's grab the session_data stored in the user's session. This will need to be compared
    # against the session_data claim in the JWT token included by the Proctoring Tool in the request. This protects
    # against CSRF attacks.
    session_data_key = get_cache_key(app="lti", key="session_data", user_id=request.user.id)
    cached_session_data = TieredCache.get_cached_response(session_data_key)
    if cached_session_data.is_found:
        session_data = cached_session_data.value
    else:
        return JsonResponse(
            {'error': 'The provided session_data claim does not match the anti-CSRF token.'},
            status=HTTP_400_BAD_REQUEST,
        )

    # TODO: The resource link should uniquely represent the assessment in the Assessment Platform.
    #       We SHOULD provide a value for the title attribute.
    #       It's RECOMMENDED to provide a value for the description attribute.
    #       The xblock-lti-consumer library does not currently support setting these attributes.
    resource_link = request.POST.get('resource_link')
    attempt_number = request.POST.get('attempt_number')

    lti_consumer.set_proctoring_data(
        attempt_number=attempt_number,
        session_data=session_data,
        resource_link=resource_link,
    )

    # TODO: I hardcoded this to None for right now. We'll need to figure out how to supply user_roles from outside the
    #       platform.
    # TODO: LTI Proctoring Services expects that the user role is empty or includes
    #       "http://purl.imsglobal.org/vocab/lis/v2/membership#Learner", which is a context role.
    #       lti_consumer.set_user_data uses the regular roles. So, for now, I'm leaving it empty.
    # Required user claim data
    lti_consumer.set_user_data(
        user_id=request.user.id,
        role=None,
    )

    # These claims are optional. They are necessary to set in order to properly verify the verified_user claim,
    # if the Proctoring Tool includes it in the JWT.
    # TODO: This will need to have additional consideration for PII.
    # optional_user_identity_claims = get_optional_user_identity_claims()
    # lti_consumer.set_proctoring_user_data(
    #     **optional_user_identity_claims
    # )

    try:
        lti_response = lti_consumer.check_and_decode_token(token)
    # TODO: This needs better error handling.
    except (BadJwtSignature, MalformedJwtToken, NoSuitableKeys):
        return JsonResponse(
            {},
            status=HTTP_400_BAD_REQUEST,
        )

    # If the Proctoring Tool specifies the end_assessment_return claim in its LTI launch request,
    # the Assessment Platform MUST send an End Assessment Message at the end of the user's
    # proctored exam.
    end_assessment_return = lti_response.get('end_assessment_return')
    if end_assessment_return:
        end_assessment_return_key = get_cache_key(app="lti", key="end_assessment_return", user_id=request.user.id)
        # We convert the boolean to an int because memcached will return an int even if a boolean is stored. This
        # ensures a consistent return value.
        end_assessment_return_value = int(end_assessment_return)
        TieredCache.set_all_tiers(end_assessment_return_key, end_assessment_return_value)

    return JsonResponse(data={})


# We do not want Django's CSRF protection enabled for POSTs made by external services to this endpoint. This is because
# Django uses the double-submit cookie method of CSRF protection, but the Proctoring Specification lends itself better
# to the synchronizer token method of CSRF protection. Django's method requires an anti-CSRF token to be included in
# both a cookie and a hidden from value in the request to CSRF procted endpoints. In the Proctoring Specification, there
# are a number of issues supporting the double-submit cookie method.
#
# 1. Django requires that a cookie containing the anti-CSRF token is sent with the request from the Proctoring Tool to
#    the Assessment Platform . When the user's browser makes a request to the launch_gate_endpoint view, an anti-CSRF
#    token is set in the cookie. The default SameSite attribute for cookies is "Lax" (stored in the Django setting
#    CSRF_COOKIE_SAMESITE), meaning that when the Proctoring Tool redirects the user's browser back to the Assessment
#    Platform, the browser will not include the previously set cookie in its request to the Assessment Platform.
#    CSRF_COOKIE_SAMESITE can be set to "None", but this means that all third-party cookies will be included by the
#    browser, which may compromise CSRF protection for other endpoints. Note that settings CSRF_COOKIE_SAMESITE to
#    "None" requires that CSRF_COOKIE_SECURE is set to True.
#
# 2. Django validates a request by comparing the above anti-CSRF token in the cookie to the anti-CSRF token in the POST
#    request parameters. Django expects the anti-CSRF token to be in the POST request parameters with the key name
#    "csrfmiddlewaretoken". However, the Proctoring Specification requires that the anti-CSRF token be included in the
#    JWT token with the name "session_data". The Proctoring Tool will not direct the browser to send this anti-CSRF
#    token back with the key name "csrfmiddlewaretoken", nor will it include it as a form parameter, as it's not part of
#    the Proctoring Services Specification.
@csrf_exempt
# Authorization Servers MUST support the use of the HTTP GET and POST methods defined in RFC 2616 [RFC2616]
# at the Authorization Endpoint.
# See 3.1.2.1.Authentication Request of the OIDC specification.
# https://openid.net/specs/openid-connect-core-1_0.html#AuthRequest
@require_http_methods(["GET", "POST"])
def launch_gate_endpoint_proctoring(request, suffix=None):  # pylint: disable=unused-argument
    """
    This is the Assessment Platform's OIDC login authentication/authorization endpoint.

    This uses the "client_id" query parameter or form data to identify the LtiConfiguration and its consumer to generate
    the LTI 1.3 Launch Form.
    """
    preflight_response = request.GET.dict() if request.method == 'GET' else request.POST.dict()

    # DECISION: We need access to the correct LtiConfiguration instance. We could use "location", but this is tied
    #           to the XBlock. We could use config_id, but that would need to be passed to this view via the URL or a
    #           query parameter by the consuming library (see launch_gate_endpoint). Instead, let's use the client_id,
    #           which is a query parameter required by the LTI 1.3 specification. This should uniquely identify the
    #           LtiConfiguration instance.
    client_id = preflight_response.get('client_id')
    if not client_id:
        log.error('The preflight response is not valid. The required parameter client_id is missing.')
        return render(request, 'html/lti_1p3_launch_error.html', status=HTTP_400_BAD_REQUEST)

    try:
        lti_config = LtiConfiguration.objects.get(
            lti_1p3_client_id=client_id,
        )
    except LtiConfiguration.DoesNotExist as exc:
        log.error("Invalid client_id '%s' for LTI 1.3 proctoring launch.", client_id)
        raise Http404 from exc

    if lti_config.version != LtiConfiguration.LTI_1P3:
        log.error("The LTI Version of configuration %s is not LTI 1.3", lti_config)
        return render(request, 'html/lti_1p3_launch_error.html', status=HTTP_404_NOT_FOUND)

    if not lti_config.lti_1p3_proctoring_enabled:
        log.error("Proctoring Services for LTIConfiguration with config_id %s are not enabled", lti_config.config_id)
        return render(request, 'html/lti_1p3_launch_error.html', status=HTTP_400_BAD_REQUEST)

    context = {}

    # TODO: The below calls are an issue, because they call to the LMS.
    # course_key = usage_key.course_key
    # course = compat.get_course_by_id(course_key)
    # user_role = compat.get_user_role(request.user, course_key)
    # external_user_id = compat.get_external_id_for_user(request.user)

    # TODO: I hardcoded this to None for right now. We'll need to figure out how to supply user_roles from outside the
    #       platform.
    # TODO: LTI Proctoring Services expects that the user role is empty or includes
    #       "http://purl.imsglobal.org/vocab/lis/v2/membership#Learner", which is a context role.
    #       lti_consumer.set_user_data uses the regular roles. So, for now, I'm leaving it empty.
    user_role = None

    course_key = "dummy_course_key"

    class DummyCourse:
        display_name_with_default = "dummy_course_name"
        display_org_with_default = "dummy_course_org"
    course = DummyCourse()

    lti_consumer = lti_config.get_lti_consumer()

    try:
        # Pass user data
        # Pass django user role to library

        # TODO: Do we need an external_id for a user within proctoring? Should edx-exams define this value?
        lti_consumer.set_user_data(user_id="dummy_user_id", role=user_role)

        # Set launch context
        # Hardcoded for now, but we need to translate from
        # self.launch_target to one of the LTI compliant names,
        # either `iframe`, `frame` or `window`
        # This is optional though
        lti_consumer.set_launch_presentation_claim('iframe')

        # TODO: The below calls are an issue, because they call to the LMS.
        # # Set context claim
        # # This is optional
        context_title = " - ".join([
            course.display_name_with_default,
            course.display_org_with_default
        ])
        # Course ID is the context ID for the LTI for now. This can be changed to be
        # more specific in the future for supporting other tools like discussions, etc.
        lti_consumer.set_context_claim(
            str(course_key),
            context_types=[LTI_1P3_CONTEXT_TYPE.course_offering],
            context_title=context_title,
            context_label=str(course_key)
        )

        # Set LTI Launch URL
        # NOTE: According to the specification, we have to post to the redirect_uri specified in the
        #       preflight response, so I have changed this.
        redirect_uri = preflight_response.get('redirect_uri')
        if not redirect_uri:
            raise PreflightRequestValidationFailure('The preflight response is not valid.'
                                                    'The required parameter redirect_uri is missing.')
        context.update({'launch_url': redirect_uri})

        lti_message_hint = preflight_response.get('lti_message_hint')
        if not lti_message_hint:
            raise PreflightRequestValidationFailure('The preflight response is not valid.'
                                                    'The required parameter lti_message_hint is invalid.')

        if lti_message_hint in ['LtiStartProctoring', 'LtiEndAssessment']:
            # "The Assessment Platform MUST also include some session-specific data (session_data) that is
            # opaque to the Proctoring Tool in the Start Proctoring message.
            # This will be returned in the Start Assessment message and acts as an anti-CSRF token,
            # the Assessment Tool MUST verify that this data matches the expected browser session
            # before actually starting the assessment."
            # See 3.3 Transferring the Candidate Back to the Assessment Platform.
            # In the synchronizer token method of CSRF protection, the anti-CSRF token must be stored on the server.
            session_data_key = get_cache_key(app="lti", key="session_data", user_id=request.user.id)

            cached_session_data = TieredCache.get_cached_response(session_data_key)
            if cached_session_data.is_found:
                session_data = cached_session_data.value
            else:
                session_data = get_random_string(32)
                TieredCache.set_all_tiers(session_data_key, session_data)

            # These claims are optional.
            # TODO: This will need to have additional consideration for PII.
            # TODO: Add the appropriate PII to the claims depending on CourseAllowPIISharingInLTIFlag;
            #       see docs/decisions/0005-lti-pii-sharing-flag.rst.
            # optional_user_identity_claims = get_optional_user_identity_claims()
            # lti_consumer.set_proctoring_user_data(
            #     **optional_user_identity_claims
            # )

            # TODO: The resource link should uniquely represent the assessment in the Assessment Platform.
            #       We SHOULD provide a value for the title attribute.
            #       It's RECOMMENDED to provide a value for the description attribute.
            #       The xblock-lti-consumer library does not currently support setting these attributes.
            resource_link = preflight_response.get('resource_link')
            start_assessment_url = preflight_response.get('start_assessment_url')
            attempt_number = preflight_response.get('attempt_number')

            lti_consumer.set_proctoring_data(
                attempt_number=attempt_number,
                session_data=session_data,
                start_assessment_url=start_assessment_url
            )
        else:
            raise PreflightRequestValidationFailure('The preflight response is not valid.'
                                                    'The required parameter lti_message_hint is invalid.')

        # Update context with LTI launch parameters
        context.update({
            "preflight_response": preflight_response,
            "launch_request": lti_consumer.generate_launch_request(
                preflight_response=preflight_response,
                resource_link=resource_link,
            )
        })
        event = {
            'lti_version': lti_config.version,
            'user_roles': user_role,
            'launch_url': context['launch_url']
        }
        # TODO: What should this be? It shouldn't be scoped to the XBlock.
        track_event('xblock.launch_request', event)

        return render(request, 'html/lti_1p3_launch.html', context)
    except Lti1p3Exception as exc:
        log.warning(
            "Error preparing LTI 1.3 launch for client_id %s: %s",
            client_id,
            exc,
            exc_info=True
        )
        return render(request, 'html/lti_1p3_launch_error.html', context, status=HTTP_400_BAD_REQUEST)
