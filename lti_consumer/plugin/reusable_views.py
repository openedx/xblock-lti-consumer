"""CMS-only management views for reusable LTI configurations."""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Exists, OuterRef, Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from lti_consumer.models import (
    ReusableLtiConfiguration,
    ReusableLtiConfigurationCourse,
    ReusableLtiConfigurationOrganization,
)
from lti_consumer.plugin import compat
from lti_consumer.plugin.reusable_permissions import can_manage_reusable_scope
from lti_consumer.plugin.reusable_serializers import (
    ReusableCreateInputSerializer,
    ReusableCreateResponseSerializer,
    ReusableDetailSerializer,
    ReusableListSerializer,
)
from lti_consumer.reusable import create_reusable_configuration


class ReusableConfigurationPagination(PageNumberPagination):
    """Bound the cross-course catalog response regardless of deployment defaults."""

    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


def _visible_configurations(user):
    """Return the same catalog visibility set used by list and detail endpoints."""
    configurations = ReusableLtiConfiguration.objects.all()
    if user.is_superuser:
        return configurations

    course_keys = compat.get_studio_accessible_course_keys(user)
    if not course_keys:
        return configurations.none()

    organization_keys = {key.org.lower() for key in course_keys}
    # shortcut: Scope equality uses database collation; review exact matching before deployment
    course_grants = ReusableLtiConfigurationCourse.objects.filter(
        configuration_id=OuterRef('pk'), course_key__in=course_keys,
    )
    organization_grants = ReusableLtiConfigurationOrganization.objects.filter(
        configuration_id=OuterRef('pk'), organization__in=organization_keys,
    )
    return configurations.alias(
        has_course=Exists(course_grants), has_organization=Exists(organization_grants),
    ).filter(Q(site_wide=True) | Q(has_course=True) | Q(has_organization=True))


def _can_manage(user, configuration, cache):
    return can_manage_reusable_scope(user, {
        'course_keys': [str(grant.course_key) for grant in configuration.course_grants.all()],
        'organization_keys': [grant.organization for grant in configuration.organization_grants.all()],
        'site_wide': configuration.site_wide,
    }, course_admin_cache=cache)


class ReusableConfigurationListCreateView(APIView):
    """List visible configurations and authorize creation against the full scope."""

    permission_classes = (IsAuthenticated,)

    def get(self, request):
        """Paginate safe metadata for configurations visible through Studio scope."""
        configurations = _visible_configurations(request.user)

        search = request.query_params.get('search')
        if search:
            configurations = configurations.filter(name__icontains=search)
        version = request.query_params.get('version')
        if version:
            configurations = configurations.filter(version=version)

        configurations = configurations.order_by('name', 'pk').prefetch_related(
            'course_grants', 'organization_grants',
        )
        paginator = ReusableConfigurationPagination()
        page = paginator.paginate_queryset(configurations, request, view=self)
        course_admin_cache = {}

        def can_manage(configuration):
            return _can_manage(request.user, configuration, course_admin_cache)

        serializer = ReusableListSerializer(page, many=True, context={'can_manage': can_manage})
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        """Validate and atomically create a complete scope-authorized configuration."""
        raw_scope = request.data.get('scope') if hasattr(request.data, 'get') else None
        # Organization and site-wide scopes are superuser-only; reject before
        # consulting the organization registry for unauthorized callers.
        if isinstance(raw_scope, dict) and (
            raw_scope.get('organization_keys') or raw_scope.get('site_wide')
        ) and not request.user.is_superuser:
            return Response(status=status.HTTP_403_FORBIDDEN)

        serializer = ReusableCreateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not can_manage_reusable_scope(request.user, serializer.validated_data['scope']):
            return Response(status=status.HTTP_403_FORBIDDEN)

        try:
            result = create_reusable_configuration(serializer.validated_data)
        except DjangoValidationError as err:
            raise serializers.ValidationError(err.messages) from err

        response_serializer = ReusableCreateResponseSerializer(
            result.configuration,
            context={
                'can_manage': True,
                'one_time_credentials': result.one_time_credentials,
            },
        )
        response = Response(response_serializer.data, status=status.HTTP_201_CREATED)
        response['Cache-Control'] = 'no-store'
        return response


class ReusableConfigurationDetailView(APIView):
    """Expose safe detail metadata only to users who can see the catalog entry."""

    permission_classes = (IsAuthenticated,)

    def get(self, request, config_id):
        """Return safe detail metadata when the user can see the configuration."""
        configuration = get_object_or_404(
            _visible_configurations(request.user).prefetch_related('course_grants', 'organization_grants'),
            config_id=config_id,
        )
        can_manage = _can_manage(request.user, configuration, {})
        serializer = ReusableDetailSerializer(
            configuration,
            context={'can_manage': can_manage},
        )
        response = Response(serializer.data)
        response['Cache-Control'] = 'no-store'
        return response
