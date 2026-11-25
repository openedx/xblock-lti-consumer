"""CMS-only HTTP adapters for reusable LTI configuration management.

These views translate requests into module calls and module failures into HTTP.
Semantic validation, authorization, transactions and persistence stay in
``lti_consumer.reusable`` and ``lti_consumer.reusable_context``.
"""
import django_filters
from django.http import Http404
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django_filters.rest_framework import DjangoFilterBackend
from edx_rest_framework_extensions.paginators import DefaultPagination
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from lti_consumer.exceptions import ReusableConfigurationError
from lti_consumer.models import ReusableLtiConfiguration
from lti_consumer.plugin.reusable_serializers import (
    ReusableCreateInputSerializer,
    ReusableCreateResponseSerializer,
    ReusableDetailSerializer,
    ReusableListSerializer,
    ReusableUpdateInputSerializer,
)
from lti_consumer.reusable import create_reusable_configuration, update_reusable_configuration
from lti_consumer.reusable_context import CONTEXT_TYPES, CreationContextPolicy

# The router's default lookup is a free-form segment; this keeps the detail route as
# narrow as the uuid converter it replaces, so a malformed identifier fails at the
# URLconf instead of inside a queryset filter.
PASSPORT_ID_PATTERN = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'


class ReusableConfigurationPagination(DefaultPagination):
    """The standard paginated envelope with this endpoint's bounded page size."""

    page_size = 20


class ReusableConfigurationFilterSet(django_filters.FilterSet):
    """List filters for the catalog; the Creation Context scope stays in the policy.

    These filters only narrow rows. ``context_type`` validity and its precedence
    ahead of ``course_key`` stay in the view, and ``version`` accepts any
    literal, so an unknown version is an empty page rather than a 400. ``search``
    keeps its parameter name and matches the name case-insensitively; no value is
    stripped, as the hand-written filters did not strip.
    """

    context_type = django_filters.CharFilter()
    version = django_filters.CharFilter(strip=False)
    search = django_filters.CharFilter(field_name='name', lookup_expr='icontains', strip=False)

    class Meta:
        model = ReusableLtiConfiguration
        fields = ('context_type', 'version', 'search')


def _field_error(field, messages):
    """Render a dotted member address in the nested DRF field-error style."""
    errors = messages
    for part in reversed(field.split('.')):
        errors = {part: errors}
    return errors


def _http_exception(error):
    """Return the framework exception for one module failure category and body style.

    A forbidden failure keeps the module's rule text off the wire, as before, and
    only gains the generic framework ``detail``.
    """
    if error.category == 'not_found':
        return Http404()
    if error.category == 'forbidden':
        return PermissionDenied()
    if error.field:
        return ValidationError(_field_error(error.field, error.messages))
    return ValidationError(error.messages)


class ReusableConfigurationViewSet(GenericViewSet):
    """Authenticated management adapter: list, create, retrieve and partial update.

    Every write goes through the mutation module rather than ``serializer.save()``,
    so no PUT or DELETE is exposed and the framework answers 405 for them.
    """

    permission_classes = (IsAuthenticated,)
    pagination_class = ReusableConfigurationPagination
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = ReusableConfigurationFilterSet
    ordering_fields = ('name', 'version', 'created_at', 'updated_at')
    ordering = ('name', 'pk')
    lookup_field = 'passport_id'
    lookup_value_regex = PASSPORT_ID_PATTERN
    action_serializers = {
        'list': ReusableListSerializer,
        'retrieve': ReusableDetailSerializer,
        'create': ReusableCreateInputSerializer,
        'partial_update': ReusableUpdateInputSerializer,
    }

    @cached_property
    def policy(self):
        """Return this request's policy; it caches the platform lookups it makes."""
        return CreationContextPolicy(self.request.user)

    def get_serializer_class(self):
        """Select the wire serializer by action; OPTIONS arrives without one."""
        serializer_class = self.action_serializers.get(self.action)
        if serializer_class is not None:
            return serializer_class
        # Metadata asks for the collection's POST body or the instance's own fields.
        if self.request.method == 'POST':
            return ReusableCreateInputSerializer
        return ReusableDetailSerializer if 'passport_id' in self.kwargs else ReusableListSerializer

    def handle_exception(self, exc):
        """Let the shared framework handler render module failures with their status."""
        if isinstance(exc, ReusableConfigurationError):
            exc = _http_exception(exc)
        return super().handle_exception(exc)

    def finalize_response(self, request, response, *args, **kwargs):
        """Cover framework responses too: parser, permission, 404 and 405 failures."""
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'no-store'
        return response

    def get_queryset(self):
        """Return the rows this actor may see; course_key is the single policy call."""
        course_key = self.request.query_params.get('course_key') if self.action == 'list' else None
        return self.policy.visible_configurations(course_key=course_key)

    def filter_queryset(self, queryset):
        """Apply the documented list filters and ordering to the list only."""
        if self.action != 'list':
            return queryset
        return super().filter_queryset(queryset)

    def list(self, request):
        """Paginate safe metadata for the configurations this actor can see."""
        # Checked before the policy reads course_key, as the hand-written filter did:
        # a blank or unknown context_type must still be reported ahead of a bad key.
        context_type = request.query_params.get('context_type')
        if context_type not in (None, *CONTEXT_TYPES):
            # Translators: course, organization and site are literal API values; do not translate them.
            raise ValidationError({'context_type': _('Use course, organization, or site.')})

        configurations = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(configurations)
        serializer = self.get_serializer(page, many=True, context={'can_manage': self.policy.can_manage})
        return self.get_paginated_response(serializer.data)

    def create(self, request):
        """Validate and atomically create one context-authorized configuration."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = create_reusable_configuration(request.user, serializer.validated_data)
        # The create succeeded, so the actor holds management authority for this context.
        response_serializer = ReusableCreateResponseSerializer(
            result.configuration,
            context={'can_manage': True, 'one_time_credentials': result.one_time_credentials},
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        """Return safe detail metadata for one visible configuration."""
        configuration = self.get_object()
        serializer = self.get_serializer(
            configuration, context={'can_manage': self.policy.can_manage(configuration)},
        )
        return Response(serializer.data)

    def partial_update(self, request, passport_id=None):
        """Update ordinary settings; context and registration identity stay immutable."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        configuration = update_reusable_configuration(request.user, passport_id, serializer.validated_data)
        # The mutation module returns the row only after its manage check passed.
        return Response(ReusableDetailSerializer(configuration, context={'can_manage': True}).data)
