"""CMS-only HTTP adapters for reusable LTI configuration management.

These views translate requests into module calls and module failures into HTTP.
Semantic validation, authorization, transactions and persistence stay in
``lti_consumer.reusable`` and ``lti_consumer.reusable_context``.
"""
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from lti_consumer.exceptions import ReusableConfigurationError
from lti_consumer.plugin.reusable_serializers import (
    ReusableCreateInputSerializer,
    ReusableCreateResponseSerializer,
    ReusableDetailSerializer,
    ReusableListSerializer,
    ReusableUpdateInputSerializer,
)
from lti_consumer.reusable import create_reusable_configuration, update_reusable_configuration
from lti_consumer.reusable_context import CONTEXT_TYPES, CreationContextPolicy


class ReusableConfigurationPagination(PageNumberPagination):
    """Bound the catalog response regardless of the deployment-wide defaults."""

    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


def _field_error(field, messages):
    """Render a dotted member address in the nested DRF field-error style."""
    errors = messages
    for part in reversed(field.split('.')):
        errors = {part: errors}
    return errors


def _error_response(error):
    """Render one module failure with its agreed status and body style."""
    if error.category == 'not_found':
        raise Http404 from None
    if error.category == 'forbidden':
        return Response(status=status.HTTP_403_FORBIDDEN)
    if error.field:
        return Response(_field_error(error.field, error.messages), status=status.HTTP_400_BAD_REQUEST)
    return Response(error.messages, status=status.HTTP_400_BAD_REQUEST)


class ReusableManagementView(APIView):
    """Authenticated management adapter whose responses must never be cached."""

    permission_classes = (IsAuthenticated,)

    def finalize_response(self, request, response, *args, **kwargs):
        """Cover framework responses too: parser, permission, 404 and 405 failures."""
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'no-store'
        return response


class ReusableConfigurationListCreateView(ReusableManagementView):
    """List the visible catalog, and create one configuration in its context."""

    def get(self, request):
        """Paginate safe metadata for the configurations this actor can see."""
        context_type = request.query_params.get('context_type')
        if context_type not in (None, *CONTEXT_TYPES):
            # Translators: course, organization and site are literal API values; do not translate them.
            raise ValidationError({'context_type': _('Use course, organization, or site.')})

        policy = CreationContextPolicy(request.user)
        try:
            configurations = policy.visible_configurations(course_key=request.query_params.get('course_key'))
        except ReusableConfigurationError as error:
            return _error_response(error)

        if context_type:
            configurations = configurations.filter(context_type=context_type)
        search = request.query_params.get('search')
        if search:
            configurations = configurations.filter(name__icontains=search)
        version = request.query_params.get('version')
        if version:
            configurations = configurations.filter(version=version)

        configurations = configurations.order_by('name', 'pk')
        paginator = ReusableConfigurationPagination()
        page = paginator.paginate_queryset(configurations, request, view=self)
        serializer = ReusableListSerializer(page, many=True, context={'can_manage': policy.can_manage})
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        """Validate and atomically create one context-authorized configuration."""
        serializer = ReusableCreateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = create_reusable_configuration(request.user, serializer.validated_data)
        except ReusableConfigurationError as error:
            return _error_response(error)

        # The create succeeded, so the actor holds management authority for this context.
        response_serializer = ReusableCreateResponseSerializer(
            result.configuration,
            context={'can_manage': True, 'one_time_credentials': result.one_time_credentials},
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class ReusableConfigurationDetailView(ReusableManagementView):
    """Expose safe detail metadata only to readers who can see the catalog entry."""

    def get(self, request, config_id):
        """Return safe detail metadata for one visible configuration."""
        policy = CreationContextPolicy(request.user)
        configuration = get_object_or_404(policy.visible_configurations(), passport_id=config_id)
        serializer = ReusableDetailSerializer(
            configuration,
            context={'can_manage': policy.can_manage(configuration)},
        )
        return Response(serializer.data)

    def patch(self, request, config_id):
        """Update ordinary settings; context and registration identity stay immutable."""
        serializer = ReusableUpdateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            configuration = update_reusable_configuration(request.user, config_id, serializer.validated_data)
        except ReusableConfigurationError as error:
            return _error_response(error)

        # The mutation module returns the row only after its manage check passed.
        return Response(ReusableDetailSerializer(configuration, context={'can_manage': True}).data)
