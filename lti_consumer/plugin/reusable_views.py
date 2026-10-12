"""CMS-only management views for reusable LTI configurations."""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Q
from django.shortcuts import get_object_or_404
from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import CourseKey
from opaque_keys.edx.locator import CourseLocator
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
    ReusableUpdateInputSerializer,
)
from lti_consumer.reusable import create_reusable_configuration


class ReusableConfigurationPagination(PageNumberPagination):
    """Bound the cross-course catalog response regardless of deployment defaults."""

    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


def _visible_configurations(user, course_key=None):
    """Return configurations visible through Studio access, optionally for one course."""
    configurations = ReusableLtiConfiguration.objects.all()
    if user.is_superuser:
        if course_key is None:
            return configurations
        course_keys = [course_key]
    else:
        accessible_course_keys = compat.get_studio_accessible_course_keys(user)
        if not accessible_course_keys or (course_key is not None and course_key not in accessible_course_keys):
            return configurations.none()
        course_keys = [course_key] if course_key is not None else accessible_course_keys

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
        raw_course_key = request.query_params.get('course_key')
        course_key = None
        if raw_course_key is not None:
            try:
                course_key = CourseKey.from_string(raw_course_key)
            except InvalidKeyError as err:
                raise serializers.ValidationError({'course_key': 'Invalid course key.'}) from err
            if not isinstance(course_key, CourseLocator):
                raise serializers.ValidationError({'course_key': 'A course key is required.'})
        configurations = _visible_configurations(request.user, course_key=course_key)

        scope = request.query_params.get('scope')
        if scope not in (None, 'course', 'organization', 'site_wide'):
            raise serializers.ValidationError({'scope': 'Use course, organization, or site_wide.'})
        if scope == 'course':
            configurations = configurations.filter(Exists(
                ReusableLtiConfigurationCourse.objects.filter(configuration_id=OuterRef('pk'))
            ))
        elif scope == 'organization':
            configurations = configurations.filter(Exists(
                ReusableLtiConfigurationOrganization.objects.filter(configuration_id=OuterRef('pk'))
            ))
        elif scope == 'site_wide':
            configurations = configurations.filter(site_wide=True)

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

    def patch(self, request, config_id):
        """Update editable metadata and add grants without permitting scope reduction."""
        try:
            with transaction.atomic():
                configuration = get_object_or_404(
                    _visible_configurations(request.user).select_for_update(),
                    config_id=config_id,
                )
                current_scope = {
                    'course_keys': [
                        str(key) for key in configuration.course_grants.values_list('course_key', flat=True)
                    ],
                    'organization_keys': list(
                        configuration.organization_grants.values_list('organization', flat=True)
                    ),
                    'site_wide': configuration.site_wide,
                }
                if not can_manage_reusable_scope(request.user, current_scope):
                    return Response(status=status.HTTP_403_FORBIDDEN)

                raw_scope = request.data.get('scope') if isinstance(request.data, dict) else None
                if isinstance(raw_scope, dict) and (
                    raw_scope.get('organization_keys') or raw_scope.get('site_wide')
                ) and not request.user.is_superuser:
                    return Response(status=status.HTTP_403_FORBIDDEN)

                serializer = ReusableUpdateInputSerializer(
                    data=request.data,
                    partial=True,
                    context={
                        'configuration': configuration,
                        'existing_organization_keys': set(current_scope['organization_keys']),
                    },
                )
                serializer.is_valid(raise_exception=True)
                changes = serializer.validated_data
                requested_scope = changes.get('scope', {})
                if current_scope['site_wide'] and requested_scope.get('site_wide') is False:
                    raise serializers.ValidationError({'scope': 'Scope reductions are not supported.'})

                proposed_scope = {
                    'course_keys': list(dict.fromkeys(
                        current_scope['course_keys'] + requested_scope.get('course_keys', [])
                    )),
                    'organization_keys': list(dict.fromkeys(
                        current_scope['organization_keys'] + requested_scope.get('organization_keys', [])
                    )),
                    'site_wide': current_scope['site_wide'] or requested_scope.get('site_wide', False),
                }
                if not can_manage_reusable_scope(request.user, proposed_scope):
                    return Response(status=status.HTTP_403_FORBIDDEN)

                scalar_fields = {
                    'name': 'name',
                    'description': 'description',
                    'launch_url': (
                        'lti_1p1_launch_url' if configuration.version == ReusableLtiConfiguration.LTI_1P1
                        else 'lti_1p3_launch_url'
                    ),
                    'oidc_url': 'lti_1p3_oidc_url',
                    'redirect_uris': 'lti_1p3_redirect_uris',
                }
                service_fields = {
                    'deep_linking_enabled': 'lti_advantage_deep_linking_enabled',
                    'deep_linking_launch_url': 'lti_advantage_deep_linking_launch_url',
                    'ags_mode': 'lti_advantage_ags_mode',
                    'nrps_enabled': 'lti_advantage_enable_nrps',
                }
                for key, field in scalar_fields.items():
                    if key in changes:
                        value = changes[key]
                        if key == 'description' and value is None:
                            value = ''
                        setattr(configuration, field, value)
                for key, field in service_fields.items():
                    if key in changes.get('services', {}):
                        value = changes['services'][key]
                        if key == 'deep_linking_launch_url' and value is None:
                            value = ''
                        setattr(configuration, field, value)
                for key, value in changes.get('defaults', {}).items():
                    setattr(configuration, key, value)
                configuration.site_wide = proposed_scope['site_wide']
                configuration.save()

                existing_courses = set(current_scope['course_keys'])
                ReusableLtiConfigurationCourse.objects.bulk_create([
                    ReusableLtiConfigurationCourse(configuration=configuration, course_key=key)
                    for key in proposed_scope['course_keys'] if key not in existing_courses
                ])
                existing_organizations = set(current_scope['organization_keys'])
                ReusableLtiConfigurationOrganization.objects.bulk_create([
                    ReusableLtiConfigurationOrganization(configuration=configuration, organization=key)
                    for key in proposed_scope['organization_keys'] if key not in existing_organizations
                ])
        except IntegrityError:
            raise serializers.ValidationError('The update conflicts with an existing configuration.') from None

        can_manage = _can_manage(request.user, configuration, {})
        response = Response(ReusableDetailSerializer(
            configuration, context={'can_manage': can_manage},
        ).data)
        response['Cache-Control'] = 'no-store'
        return response
