"""
REST API for reusable LTI configurations, guarded by their context's permissions.

``Lti1p3Passport`` stands in for the reusable configuration model until that
model exists.
"""

from urllib.parse import urlparse

from django.shortcuts import get_object_or_404
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import SAFE_METHODS, BasePermission, IsAuthenticated
from rest_framework.response import Response

from lti_consumer.models import Lti1p3Passport

from .permissions import CONFIGURATION_ACTIONS, EDIT_CONFIGURATION, VIEW_CONFIGURATION, user_has_configuration_permission


class ReusableLtiConfigurationSerializer(serializers.ModelSerializer):
    """
    The minimal view of a configuration: enough to recognise and pick it, nothing sensitive.

    The context is read-only because a configuration's context is fixed at creation.
    """

    launch_domain = serializers.SerializerMethodField()

    class Meta:
        model = Lti1p3Passport
        fields = ["passport_id", "name", "context_key", "launch_domain"]
        read_only_fields = ["passport_id", "context_key"]

    def get_launch_domain(self, obj):
        """
        Return the tool's host. The passport has no launch URL, so use its keyset URL.
        """
        return urlparse(obj.lti_1p3_tool_keyset_url).hostname


class CanAccessLtiConfiguration(BasePermission):
    """
    Reads need view permission on the configuration's context; writes need edit permission.
    """

    def has_object_permission(self, request, view, obj):
        permission = VIEW_CONFIGURATION if request.method in SAFE_METHODS else EDIT_CONFIGURATION
        return user_has_configuration_permission(request.user, permission, obj)


class ReusableLtiConfigurationViewSet(mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """
    Retrieve and update reusable LTI configurations.

    ``GET <passport_id>`` returns the minimal view, ``PATCH <passport_id>`` renames
    the configuration, and ``GET <passport_id>/permissions`` reports what the
    requesting user may do with it.
    """

    queryset = Lti1p3Passport.objects.all()
    lookup_field = "passport_id"
    serializer_class = ReusableLtiConfigurationSerializer
    permission_classes = [IsAuthenticated, CanAccessLtiConfiguration]

    @action(detail=True, methods=["get"], permission_classes=[IsAuthenticated])
    def permissions(self, request, passport_id=None):
        """
        Return ``{action: allowed}`` for each configuration action.

        This skips the view check so that a user with no access gets all-false
        rather than an error.
        """
        config = get_object_or_404(self.get_queryset(), passport_id=passport_id)
        return Response({
            name: user_has_configuration_permission(request.user, permission, config)
            for name, permission in CONFIGURATION_ACTIONS.items()
        })
