"""Strict wire parsing and allowlisted rendering for reusable LTI configurations.

These serializers only convert JSON primitives and choose response fields. Semantic
validation, authorization and merged-state checks stay in ``lti_consumer.reusable``
and ``lti_consumer.reusable_context``, so a non-HTTP caller is validated the same
way and this module carries no domain rules.
"""
# Parse/render-only DRF wire serializers: they never implement create or update.
# pylint: disable=abstract-method
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from lti_consumer.models import ReusableLtiConfiguration
from lti_consumer.utils import (
    get_lms_lti_access_token_link,
    get_lms_lti_keyset_link,
    get_lms_lti_launch_link,
)


class StrictSerializer(serializers.Serializer):
    """Reject unknown members instead of silently dropping possibly sensitive input."""

    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({key: [_('Unknown field.')] for key in sorted(unknown)})
        return super().to_internal_value(data)


class ReusableContextInputSerializer(StrictSerializer):
    """Parse a context shape; the policy normalizes and authorizes it."""

    type = serializers.CharField(allow_blank=True)
    key = serializers.CharField(required=False, allow_blank=True)


class ReusableLti11CreateInputSerializer(StrictSerializer):
    """Parse LTI 1.1 creation primitives, optional credentials included."""

    launch_url = serializers.CharField(allow_blank=True)
    client_key = serializers.CharField(required=False, allow_blank=True)
    client_secret = serializers.CharField(required=False, allow_blank=True)


class ReusableLti13CreateInputSerializer(StrictSerializer):
    """Parse LTI 1.3 creation and registration identity primitives."""

    launch_url = serializers.CharField(allow_blank=True)
    oidc_url = serializers.CharField(allow_blank=True)
    tool_key_mode = serializers.CharField(allow_blank=True)
    redirect_uris = serializers.ListField(child=serializers.CharField(allow_blank=True), required=False)
    tool_public_key = serializers.CharField(required=False, allow_blank=True)
    tool_keyset_url = serializers.CharField(required=False, allow_blank=True)
    client_id = serializers.CharField(required=False, allow_blank=True)
    deployment_id = serializers.CharField(required=False, allow_blank=True)


class ReusableLti11UpdateInputSerializer(StrictSerializer):
    """Parse editable LTI 1.1 settings, but never the issued credentials."""

    launch_url = serializers.CharField(required=False, allow_blank=True)


class ReusableLti13UpdateInputSerializer(StrictSerializer):
    """Parse editable LTI 1.3 tool settings, but never the registration identity."""

    launch_url = serializers.CharField(required=False, allow_blank=True)
    oidc_url = serializers.CharField(required=False, allow_blank=True)
    redirect_uris = serializers.ListField(child=serializers.CharField(allow_blank=True), required=False)
    tool_key_mode = serializers.CharField(required=False, allow_blank=True)
    tool_public_key = serializers.CharField(required=False, allow_blank=True)
    tool_keyset_url = serializers.CharField(required=False, allow_blank=True)


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
    hide_external_tool = serializers.BooleanField(required=False)


class ReusablePrivacyInputSerializer(StrictSerializer):
    """Parse privacy selections; pii_* stored names never appear on the wire."""

    share_username = serializers.BooleanField(required=False)
    share_full_name = serializers.BooleanField(required=False)
    share_email = serializers.BooleanField(required=False)
    data_sharing_notice = serializers.CharField(required=False, allow_blank=True)
    require_user_confirmation = serializers.BooleanField(required=False)


class ReusableCreateInputSerializer(StrictSerializer):
    """Parse a complete create request; the mutation module validates it."""

    name = serializers.CharField(allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    version = serializers.CharField(allow_blank=True)
    context = ReusableContextInputSerializer()
    lti_1p1 = ReusableLti11CreateInputSerializer(required=False)
    lti_1p3 = ReusableLti13CreateInputSerializer(required=False)
    services = ReusableServicesInputSerializer(required=False)
    defaults = ReusableDefaultsInputSerializer(required=False)
    privacy = ReusablePrivacyInputSerializer(required=False)


class ReusableUpdateInputSerializer(StrictSerializer):
    """Parse one PATCH; the mutation module validates it against the stored row.

    A context member is accepted only for a converted row's one-time assignment and a
    version member only for its one-time initialization; both rules stay in the module.
    """

    name = serializers.CharField(required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    # Creation accepts any literal and lets the module judge it; a PATCH version is a
    # one-time choice from the two known values, so it is constrained at the wire here.
    version = serializers.ChoiceField(choices=ReusableLtiConfiguration.LTI_VERSION_CHOICES, required=False)
    context = ReusableContextInputSerializer(required=False)
    lti_1p1 = ReusableLti11UpdateInputSerializer(required=False)
    lti_1p3 = ReusableLti13UpdateInputSerializer(required=False)
    services = ReusableServicesInputSerializer(required=False)
    defaults = ReusableDefaultsInputSerializer(required=False)
    privacy = ReusablePrivacyInputSerializer(required=False)


class ReusableListSerializer(serializers.Serializer):
    """Allowlisted metadata safe for any reader who may see the configuration."""

    # The wire keeps its own name; identity is stored as passport_id.
    config_id = serializers.UUIDField(source='passport_id', read_only=True)
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
        """Render only an assigned context: site carries no key and a converted row's raw key stays hidden."""
        if obj.context_type is None:
            return None
        if obj.context_type == 'site':
            return {'type': 'site'}
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
    tool_key_mode = serializers.CharField(source='lti_1p3_tool_key_mode', read_only=True)
    tool_key_configured = serializers.SerializerMethodField()
    client_id = serializers.SerializerMethodField()
    deployment_id = serializers.SerializerMethodField()
    registration_urls = serializers.SerializerMethodField()
    deep_linking_launch_url = serializers.CharField(
        source='lti_advantage_deep_linking_launch_url',
        read_only=True,
    )
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
    hide_external_tool = serializers.BooleanField(read_only=True)
    privacy = serializers.SerializerMethodField()

    def get_launch_url(self, obj):
        """Return the stored launch URL for the assigned version; none is inferred without one."""
        if obj.version == ReusableLtiConfiguration.LTI_1P1:
            return obj.lti_1p1_launch_url
        if obj.version == ReusableLtiConfiguration.LTI_1P3:
            return obj.lti_1p3_launch_url
        # No version yet: the row stores no launch URL and none is inferred.
        return None

    def get_oidc_url(self, obj):
        return None if obj.version == ReusableLtiConfiguration.LTI_1P1 else obj.lti_1p3_oidc_url

    def get_redirect_uris(self, obj):
        return [] if obj.version == ReusableLtiConfiguration.LTI_1P1 else obj.lti_1p3_redirect_uris

    def get_tool_key_configured(self, obj):
        """Report stored tool-key presence only, never validity, readiness or key text."""
        if obj.version == ReusableLtiConfiguration.LTI_1P1:
            return False
        return bool(obj.lti_1p3_tool_public_key or obj.lti_1p3_tool_keyset_url)

    def get_client_id(self, obj):
        return None if obj.version == ReusableLtiConfiguration.LTI_1P1 else obj.lti_1p3_client_id

    def get_deployment_id(self, obj):
        return None if obj.version == ReusableLtiConfiguration.LTI_1P1 else obj.lti_1p3_deployment_id

    def get_registration_urls(self, obj):
        """Resolve the LMS endpoints a tool registers against; no CMS reverse names exist."""
        if obj.version != ReusableLtiConfiguration.LTI_1P3:
            return {}
        return {
            'login_url': get_lms_lti_launch_link(),
            'jwks_url': get_lms_lti_keyset_link(obj.passport_id),
            'access_token_url': get_lms_lti_access_token_link(obj.passport_id),
        }

    def get_privacy(self, obj):
        return {
            'share_username': obj.pii_share_username,
            'share_full_name': obj.pii_share_full_name,
            'share_email': obj.pii_share_email,
            'data_sharing_notice': obj.data_sharing_notice,
            'require_user_confirmation': obj.require_user_confirmation,
        }


class ReusableCreateResponseSerializer(ReusableDetailSerializer):
    """Creation response: detail plus the one-time LTI 1.1 credentials, when issued."""

    one_time_credentials = serializers.SerializerMethodField()

    def get_one_time_credentials(self, _obj):
        return self.context.get('one_time_credentials')

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not self.context.get('one_time_credentials'):
            data.pop('one_time_credentials', None)
        return data
