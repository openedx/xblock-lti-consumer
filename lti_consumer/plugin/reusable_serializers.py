"""Wire parsing and safe rendering for reusable LTI configurations.

These serializers only convert JSON primitives, refuse unknown members, and
allowlist response fields. Semantic validation belongs to lti_consumer.reusable.
"""
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from lti_consumer.models import ReusableLtiConfiguration
from lti_consumer.utils import (
    get_lti_api_base,
    get_lti_view_base,
)


class StrictSerializer(serializers.Serializer):
    """Reject unknown keys instead of silently dropping potentially sensitive input."""

    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({key: [_('Unknown field.')] for key in sorted(unknown)})
        return super().to_internal_value(data)


class ReusableContextInputSerializer(StrictSerializer):
    """Parse the create-only context shape; the policy normalizes and authorizes it."""

    type = serializers.CharField()
    key = serializers.CharField(required=False, allow_blank=True)


class ReusableLti11InputSerializer(StrictSerializer):
    """Parse LTI 1.1 connection primitives."""

    launch_url = serializers.CharField()
    client_key = serializers.CharField(required=False, allow_blank=True)
    client_secret = serializers.CharField(required=False, allow_blank=True)


class ReusableLti13InputSerializer(StrictSerializer):
    """Parse LTI 1.3 connection and identity primitives."""

    launch_url = serializers.CharField()
    oidc_url = serializers.CharField()
    redirect_uris = serializers.ListField(child=serializers.CharField(allow_blank=True), required=False)
    tool_key_mode = serializers.CharField()
    tool_public_key = serializers.CharField(required=False, allow_blank=True)
    tool_keyset_url = serializers.CharField(required=False, allow_blank=True)
    client_id = serializers.CharField(required=False, allow_blank=True)
    deployment_id = serializers.CharField(required=False, allow_blank=True)


class ReusableServicesInputSerializer(StrictSerializer):
    """Parse LTI Advantage service settings without enforcing their rules."""

    deep_linking_enabled = serializers.BooleanField(required=False)
    deep_linking_launch_url = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    ags_mode = serializers.CharField(required=False, allow_blank=True)
    nrps_enabled = serializers.BooleanField(required=False)


class ReusableDefaultsInputSerializer(StrictSerializer):
    """Parse placement default primitives without enforcing their ranges."""

    display_name = serializers.CharField(required=False, allow_blank=True)
    enable_grading = serializers.BooleanField(required=False)
    grade_weight = serializers.FloatField(required=False)
    accept_grades_after_due_date = serializers.BooleanField(required=False)
    open_tool_in = serializers.CharField(required=False, allow_blank=True)
    inline_height = serializers.IntegerField(required=False)
    modal_height = serializers.IntegerField(required=False)
    modal_width = serializers.IntegerField(required=False)
    launch_button_text = serializers.CharField(required=False, allow_blank=True)
    send_extra_parameters = serializers.BooleanField(required=False)
    custom_parameters = serializers.ListField(child=serializers.CharField(allow_blank=True), required=False)


class ReusableCreateInputSerializer(StrictSerializer):
    """Parse a complete create request; the mutation module validates it."""

    name = serializers.CharField(allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    version = serializers.CharField()
    context = ReusableContextInputSerializer()
    lti_1p1 = ReusableLti11InputSerializer(required=False)
    lti_1p3 = ReusableLti13InputSerializer(required=False)
    services = ReusableServicesInputSerializer(required=False)
    defaults = ReusableDefaultsInputSerializer(required=False)


class ReusableLti11UpdateInputSerializer(StrictSerializer):
    """Parse editable LTI 1.1 connection settings, but not credentials."""

    launch_url = serializers.CharField(required=False, allow_blank=True)


class ReusableLti13UpdateInputSerializer(StrictSerializer):
    """Parse editable LTI 1.3 tool settings, but not registration identity."""

    launch_url = serializers.CharField(required=False, allow_blank=True)
    oidc_url = serializers.CharField(required=False, allow_blank=True)
    redirect_uris = serializers.ListField(child=serializers.CharField(allow_blank=True), required=False)
    tool_key_mode = serializers.CharField(required=False, allow_blank=True)
    tool_public_key = serializers.CharField(required=False, allow_blank=True)
    tool_keyset_url = serializers.CharField(required=False, allow_blank=True)


class ReusableUpdateInputSerializer(StrictSerializer):
    """Parse an ordinary-settings PATCH; the mutation module validates merged state."""

    name = serializers.CharField(required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    lti_1p1 = ReusableLti11UpdateInputSerializer(required=False)
    lti_1p3 = ReusableLti13UpdateInputSerializer(required=False)
    services = ReusableServicesInputSerializer(required=False)
    defaults = ReusableDefaultsInputSerializer(required=False)


class ReusableListSerializer(serializers.Serializer):
    """Allowlisted metadata safe for any user authorized to see a configuration."""

    config_id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    version = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    can_manage = serializers.SerializerMethodField()
    deep_linking_enabled = serializers.BooleanField(source='lti_advantage_deep_linking_enabled', read_only=True)
    ags_mode = serializers.CharField(source='lti_advantage_ags_mode', read_only=True)
    nrps_enabled = serializers.BooleanField(source='lti_advantage_enable_nrps', read_only=True)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['context'] = self.get_context(instance)
        return data

    def get_context(self, obj):
        context = {'type': obj.context_type}
        if obj.context_key:
            context['key'] = obj.context_key
        return context

    def get_can_manage(self, obj):
        value = self.context.get('can_manage', False)
        return value(obj) if callable(value) else bool(value)


class ReusableDetailSerializer(ReusableListSerializer):
    """Allowlisted editable metadata; credentials and tool/platform key text are excluded."""

    description = serializers.CharField(read_only=True)
    launch_url = serializers.SerializerMethodField()
    oidc_url = serializers.SerializerMethodField()
    redirect_uris = serializers.SerializerMethodField()
    tool_key_mode = serializers.CharField(read_only=True, source='lti_1p3_tool_key_mode')
    tool_key_configured = serializers.SerializerMethodField()
    client_id = serializers.SerializerMethodField()
    deployment_id = serializers.SerializerMethodField()
    registration_urls = serializers.SerializerMethodField()
    display_name = serializers.CharField(read_only=True)
    enable_grading = serializers.BooleanField(read_only=True)
    grade_weight = serializers.FloatField(read_only=True)
    accept_grades_after_due_date = serializers.BooleanField(read_only=True)
    open_tool_in = serializers.CharField(read_only=True)
    inline_height = serializers.IntegerField(read_only=True)
    modal_height = serializers.IntegerField(read_only=True)
    modal_width = serializers.IntegerField(read_only=True)
    launch_button_text = serializers.CharField(read_only=True)
    send_extra_parameters = serializers.BooleanField(read_only=True)
    custom_parameters = serializers.ListField(child=serializers.CharField(), read_only=True)
    deep_linking_launch_url = serializers.CharField(source='lti_advantage_deep_linking_launch_url', read_only=True)

    def get_launch_url(self, obj):
        if obj.version == ReusableLtiConfiguration.LTI_1P1:
            return obj.lti_1p1_launch_url
        return obj.lti_1p3_launch_url

    def get_oidc_url(self, obj):
        return obj.lti_1p3_oidc_url if obj.version == ReusableLtiConfiguration.LTI_1P3 else None

    def get_redirect_uris(self, obj):
        return obj.lti_1p3_redirect_uris if obj.version == ReusableLtiConfiguration.LTI_1P3 else []

    def get_tool_key_configured(self, obj):
        return bool(obj.lti_1p3_passport_id) if obj.version == ReusableLtiConfiguration.LTI_1P3 else False

    def get_client_id(self, obj):
        return obj.lti_1p3_client_id if obj.version == ReusableLtiConfiguration.LTI_1P3 else None

    def get_deployment_id(self, obj):
        return obj.lti_1p3_deployment_id if obj.version == ReusableLtiConfiguration.LTI_1P3 else None

    def get_registration_urls(self, obj):
        if obj.version != ReusableLtiConfiguration.LTI_1P3:
            return {}
        return {
            'login_url': f'{get_lti_view_base()}/api/lti_consumer/v1/launch/',
            'jwks_url': f'{get_lti_api_base()}/api/lti_consumer/v1/public_keysets',
            'access_token_url': f'{get_lti_api_base()}/api/lti_consumer/v1/token',
        }


class ReusableCreateResponseSerializer(ReusableDetailSerializer):
    """Creation-only wrapper for optional one-time LTI 1.1 credentials."""

    one_time_credentials = serializers.SerializerMethodField()

    def get_one_time_credentials(self, obj):
        return self.context.get('one_time_credentials')

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not self.context.get('one_time_credentials'):
            data.pop('one_time_credentials', None)
        return data
