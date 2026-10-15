"""CMS-only management views for reusable LTI configurations."""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from opaque_keys import InvalidKeyError
from opaque_keys.edx.locator import CourseLocator
from rest_framework import serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from lti_consumer.models import ReusableLtiConfiguration
from lti_consumer.plugin import compat
from lti_consumer.plugin.reusable_keys import normalize_course_key
from lti_consumer.plugin.reusable_permissions import can_manage_reusable_context
from lti_consumer.plugin.reusable_serializers import (
    ReusableCreateInputSerializer,
    ReusableCreateResponseSerializer,
    ReusableDetailSerializer,
    ReusableListSerializer,
    ReusableUpdateInputSerializer,
)
from lti_consumer.reusable import create_reusable_configuration, service_configuration_values


class ReusableConfigurationPagination(PageNumberPagination):
    """Bound the cross-course catalog response regardless of deployment defaults."""

    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


def _visible_configurations(user, course_key=None):
    """Return configurations whose context covers the user's Studio-accessible courses."""
    configurations = ReusableLtiConfiguration.objects.all()
    if course_key is not None:
        try:
            course_key = normalize_course_key(course_key)
        except (InvalidKeyError, TypeError, ValueError):
            return configurations.none()
        if not isinstance(course_key, CourseLocator):
            return configurations.none()

    if user.is_superuser:
        if course_key is None:
            return configurations
        course_keys = [course_key]
    else:
        try:
            accessible_course_keys = [
                normalize_course_key(key) for key in compat.get_studio_accessible_course_keys(user)
            ]
        except (InvalidKeyError, TypeError, ValueError):
            return configurations.none()
        course_keys = [key for key in accessible_course_keys if isinstance(key, CourseLocator)]
        if not course_keys or (course_key is not None and course_key not in course_keys):
            return configurations.none()
        course_keys = [course_key] if course_key is not None else course_keys

    return configurations.filter(
        Q(context_type='site') |
        Q(context_type='course', context_key__in=[str(key) for key in course_keys]) |
        Q(context_type='organization', context_key__in={key.org.lower() for key in course_keys})
    )


def _can_manage(user, configuration, cache):
    return can_manage_reusable_context(
        user, configuration.context_type, configuration.context_key, course_admin_cache=cache,
    )


class ReusableConfigurationListCreateView(APIView):
    """List visible configurations and authorize creation against the creation context."""

    permission_classes = (IsAuthenticated,)

    def get(self, request):
        """Paginate safe metadata for configurations visible through Studio access."""
        raw_course_key = request.query_params.get('course_key')
        course_key = None
        if raw_course_key is not None:
            try:
                course_key = normalize_course_key(raw_course_key)
            except (InvalidKeyError, TypeError, ValueError) as err:
                raise serializers.ValidationError({'course_key': _('Invalid course key.')}) from err
            if not isinstance(course_key, CourseLocator):
                raise serializers.ValidationError({'course_key': _('A course key is required.')})
        configurations = _visible_configurations(request.user, course_key=course_key)

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
        course_admin_cache = {}

        def can_manage(configuration):
            return _can_manage(request.user, configuration, course_admin_cache)

        serializer = ReusableListSerializer(page, many=True, context={'can_manage': can_manage})
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        """Validate and atomically create a complete context-authorized configuration."""
        raw_context = request.data.get('context') if hasattr(request.data, 'get') else None
        raw_context_type = raw_context.get('type') if isinstance(raw_context, dict) else None
        # Organization and site contexts are superuser-only; reject before the
        # serializer consults the organization registry for unauthorized callers.
        if raw_context_type in ('organization', 'site') and not request.user.is_superuser:
            return Response(status=status.HTTP_403_FORBIDDEN)

        serializer = ReusableCreateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        context = serializer.validated_data['context']
        if not can_manage_reusable_context(request.user, context['type'], context.get('key', '')):
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
            _visible_configurations(request.user),
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
        """Update editable metadata and settings; the creation context is immutable."""
        try:
            with transaction.atomic():
                configuration = get_object_or_404(
                    _visible_configurations(request.user).select_for_update(),
                    config_id=config_id,
                )
                if not _can_manage(request.user, configuration, {}):
                    return Response(status=status.HTTP_403_FORBIDDEN)

                serializer = ReusableUpdateInputSerializer(
                    data=request.data,
                    partial=True,
                    context={'configuration': configuration},
                )
                serializer.is_valid(raise_exception=True)
                changes = serializer.validated_data

                scalar_fields = {'name': 'name', 'description': 'description'}
                if configuration.version == ReusableLtiConfiguration.LTI_1P1:
                    connection_changes = changes.get('lti_1p1', {})
                    connection_fields = {'launch_url': 'lti_1p1_launch_url'}
                else:
                    connection_changes = changes.get('lti_1p3', {})
                    connection_fields = {
                        'launch_url': 'lti_1p3_launch_url',
                        'oidc_url': 'lti_1p3_oidc_url',
                        'redirect_uris': 'lti_1p3_redirect_uris',
                    }
                    if 'tool_key_mode' in connection_changes:
                        configuration.lti_1p3_tool_key_mode = connection_changes['tool_key_mode']
                scalar_fields.update(connection_fields)
                for key, field in scalar_fields.items():
                    values = connection_changes if key in connection_fields else changes
                    if key in values:
                        value = values[key]
                        if key == 'description' and value is None:
                            value = ''
                        setattr(configuration, field, value)
                for field, value in service_configuration_values(changes.get('services', {})).items():
                    setattr(configuration, field, value)
                for key, value in changes.get('defaults', {}).items():
                    setattr(configuration, key, value)
                configuration.save()

                if configuration.version == ReusableLtiConfiguration.LTI_1P3 and any(
                    key in connection_changes for key in ('tool_key_mode', 'tool_public_key', 'tool_keyset_url')
                ):
                    passport = configuration.lti_1p3_passport
                    mode = connection_changes.get('tool_key_mode', configuration.lti_1p3_tool_key_mode)
                    if mode == 'public_key':
                        passport.lti_1p3_tool_public_key = connection_changes.get(
                            'tool_public_key', passport.lti_1p3_tool_public_key,
                        )
                        passport.lti_1p3_tool_keyset_url = ''
                    else:
                        passport.lti_1p3_tool_public_key = ''
                        passport.lti_1p3_tool_keyset_url = connection_changes.get(
                            'tool_keyset_url', passport.lti_1p3_tool_keyset_url,
                        )
                    passport.save(update_fields=['lti_1p3_tool_public_key', 'lti_1p3_tool_keyset_url'])
        except IntegrityError:
            raise serializers.ValidationError(_('The update conflicts with an existing configuration.')) from None

        can_manage = _can_manage(request.user, configuration, {})
        response = Response(ReusableDetailSerializer(
            configuration, context={'can_manage': can_manage},
        ).data)
        response['Cache-Control'] = 'no-store'
        return response
