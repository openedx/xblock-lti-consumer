"""CMS-only HTTP adapters for reusable LTI configuration management.

These views translate requests into module calls and module errors into HTTP.
Semantic validation, authorization, transactions and persistence stay in
lti_consumer.reusable and lti_consumer.reusable_context.
"""
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

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
from lti_consumer.reusable_context import CreationContextPolicy


class ReusableConfigurationPagination(PageNumberPagination):
    """Bound the cross-course catalog response regardless of deployment defaults."""

    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


def _field_error(field, messages):
    """Render a dotted member address as the nested DRF field-error style."""
    errors = messages
    for part in reversed(field.split('.')):
        errors = {part: errors}
    return errors


def _error_response(error):
    """Render one module error with the existing statuses and DRF response styles."""
    if error.category == 'not_found':
        raise Http404(f'No {ReusableLtiConfiguration._meta.object_name} matches the given query.')
    if error.category == 'forbidden':
        return Response(status=status.HTTP_403_FORBIDDEN)
    if error.field:
        return Response(_field_error(error.field, error.messages), status=status.HTTP_400_BAD_REQUEST)
    return Response(error.messages, status=status.HTTP_400_BAD_REQUEST)


class ReusableConfigurationListCreateView(APIView):
    """List the visible catalog and create one configuration in its context."""

    permission_classes = (IsAuthenticated,)

    def get(self, request):
        """Paginate safe metadata for configurations visible through Studio access."""
        policy = CreationContextPolicy(request.user)
        try:
            configurations = policy.visible_configurations(course_key=request.query_params.get('course_key'))
        except ReusableConfigurationError as error:
            return _error_response(error)

        context_type = request.query_params.get('context_type')
        if context_type not in (None, 'course', 'organization', 'site'):
            # Translators: course, organization and site are literal API values; do not translate them.
            raise serializers.ValidationError({'context_type': _('Use course, organization, or site.')})
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
        """Validate and atomically create a complete context-authorized configuration."""
        serializer = ReusableCreateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = create_reusable_configuration(request.user, serializer.validated_data)
        except ReusableConfigurationError as error:
            return _error_response(error)

        response_serializer = ReusableCreateResponseSerializer(
            result.configuration,
            # Creation succeeded, so the actor holds management authority for this context.
            context={'can_manage': True, 'one_time_credentials': result.one_time_credentials},
        )
        response = Response(response_serializer.data, status=status.HTTP_201_CREATED)
        response['Cache-Control'] = 'no-store'
        return response


class ReusableConfigurationDetailView(APIView):
    """Expose safe detail metadata only to users who can see the catalog entry."""

    permission_classes = (IsAuthenticated,)

    def get(self, request, config_id):
        """Return safe detail metadata when the user can see the configuration."""
        policy = CreationContextPolicy(request.user)
        configuration = get_object_or_404(policy.visible_configurations(), config_id=config_id)
        serializer = ReusableDetailSerializer(
            configuration,
            context={'can_manage': policy.can_manage(configuration)},
        )
        response = Response(serializer.data)
        response['Cache-Control'] = 'no-store'
        return response

    def patch(self, request, config_id):
        """Update ordinary settings; the Creation Context and identity stay immutable."""
        serializer = ReusableUpdateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            configuration = update_reusable_configuration(request.user, config_id, serializer.validated_data)
        except ReusableConfigurationError as error:
            return _error_response(error)

        response = Response(ReusableDetailSerializer(
            configuration,
            # The mutation module returns the row only after the manage check passed.
            context={'can_manage': True},
        ).data)
        response['Cache-Control'] = 'no-store'
        return response
