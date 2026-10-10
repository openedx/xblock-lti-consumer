"""CMS-only management views for reusable LTI configurations."""
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from lti_consumer.plugin.reusable_permissions import can_manage_reusable_scope
from lti_consumer.plugin.reusable_serializers import (
    ReusableCreateInputSerializer,
    ReusableCreateResponseSerializer,
)
from lti_consumer.reusable import create_reusable_configuration


class ReusableConfigurationCreateView(APIView):
    """Create a reusable configuration after checking authorization for its scope."""

    permission_classes = (IsAuthenticated,)

    def post(self, request):
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
