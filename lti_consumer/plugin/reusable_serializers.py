"""Strict request and safe response serializers for reusable LTI configurations."""
from math import isfinite
from urllib.parse import urlsplit

from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import CourseKey
from rest_framework import serializers

from lti_consumer.models import ReusableLtiConfiguration
from lti_consumer.plugin import compat
from lti_consumer.utils import (
    choose_lti_1p3_redirect_uris,
    get_lti_api_base,
    get_lti_view_base,
)


class StrictSerializer(serializers.Serializer):
    """Reject unknown keys instead of silently dropping potentially sensitive input."""

    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({key: ['Unknown field.'] for key in sorted(unknown)})
        return super().to_internal_value(data)


class HttpUrlField(serializers.URLField):
    """A URL field restricted to HTTP(S)."""

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        if urlsplit(value).scheme.lower() not in ('http', 'https'):
            raise serializers.ValidationError('Enter a valid HTTP(S) URL.')
        return value


class CourseKeyStringField(serializers.CharField):
    """Validate a course opaque key and keep the service's string input contract."""

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        try:
            course_key = CourseKey.from_string(value)
        except InvalidKeyError as err:
            raise serializers.ValidationError('Invalid course key.') from err
        return str(course_key)


class ReusableScopeInputSerializer(StrictSerializer):
    course_keys = serializers.ListField(child=CourseKeyStringField(allow_blank=False), required=False, default=list)
    organization_keys = serializers.ListField(
        child=serializers.CharField(allow_blank=False), required=False, default=list
    )
    site_wide = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        if not (attrs['course_keys'] or attrs['organization_keys'] or attrs['site_wide']):
            raise serializers.ValidationError('At least one scope grant is required.')
        attrs['course_keys'] = list(dict.fromkeys(key.strip() for key in attrs['course_keys']))
        attrs['organization_keys'] = list(dict.fromkeys(key.strip().lower() for key in attrs['organization_keys']))
        if any(not key for key in (*attrs['course_keys'], *attrs['organization_keys'])):
            raise serializers.ValidationError('Scope grants must be non-empty strings.')
        if attrs['organization_keys']:
            registered = {}
            for organization in compat.get_active_organizations():
                short_name = organization.get('short_name')
                if isinstance(short_name, str):
                    registered.setdefault(short_name.lower(), set()).add(short_name)

            ambiguous = [key for key in attrs['organization_keys'] if len(registered.get(key, ())) > 1]
            unknown = [key for key in attrs['organization_keys'] if key not in registered]
            if ambiguous or unknown:
                raise serializers.ValidationError({
                    'organization_keys': ['Organization must match one unambiguous active registered organization.']
                })
        return attrs


class ReusableLti11InputSerializer(StrictSerializer):
    launch_url = HttpUrlField(max_length=255)
    client_key = serializers.CharField(max_length=255, required=False, allow_blank=False)
    client_secret = serializers.CharField(max_length=255, required=False, allow_blank=False)


class ReusableLti13InputSerializer(StrictSerializer):
    launch_url = HttpUrlField(max_length=255)
    oidc_url = HttpUrlField(max_length=255)
    redirect_uris = serializers.ListField(child=HttpUrlField(), required=False, default=list)
    tool_key_mode = serializers.ChoiceField(choices=('public_key', 'keyset_url'))
    tool_public_key = serializers.CharField(required=False, allow_blank=False)
    tool_keyset_url = HttpUrlField(required=False)
    client_id = serializers.CharField(max_length=255, required=False, allow_blank=False)
    deployment_id = serializers.CharField(max_length=255, required=False, allow_blank=False)

    def validate(self, attrs):
        mode = attrs['tool_key_mode']
        if mode == 'public_key':
            key = attrs.get('tool_public_key', '')
            if not key or attrs.get('tool_keyset_url'):
                raise serializers.ValidationError('Public-key mode requires only a tool public key.')
            if 'PRIVATE KEY' in key:
                raise serializers.ValidationError({'tool_public_key': 'Private keys are not accepted.'})
        elif not attrs.get('tool_keyset_url') or attrs.get('tool_public_key'):
            raise serializers.ValidationError('Keyset mode requires only a tool keyset URL.')
        return attrs


class ReusableServicesInputSerializer(StrictSerializer):
    deep_linking_enabled = serializers.BooleanField(required=False, default=False)
    deep_linking_launch_url = HttpUrlField(max_length=225, required=False, allow_blank=True, allow_null=True)
    ags_mode = serializers.ChoiceField(
        choices=('disabled', 'declarative', 'programmatic'), required=False, default='declarative'
    )
    nrps_enabled = serializers.BooleanField(required=False, default=False)


class ReusableDefaultsInputSerializer(StrictSerializer):
    display_name = serializers.CharField(max_length=255, required=False)
    enable_grading = serializers.BooleanField(required=False)
    grade_weight = serializers.FloatField(min_value=0, required=False)
    accept_grades_after_due_date = serializers.BooleanField(required=False)
    open_tool_in = serializers.ChoiceField(choices=('iframe', 'modal', 'new_window'), required=False)
    inline_height = serializers.IntegerField(min_value=0, required=False)
    modal_height = serializers.IntegerField(min_value=0, max_value=100, required=False)
    modal_width = serializers.IntegerField(min_value=0, max_value=100, required=False)
    launch_button_text = serializers.CharField(max_length=255, required=False, allow_blank=True)
    send_extra_parameters = serializers.BooleanField(required=False)
    custom_parameters = serializers.ListField(
        child=serializers.CharField(), required=False
    )

    def validate_grade_weight(self, value):
        if not isfinite(value):
            raise serializers.ValidationError('A finite grade weight is required.')
        return value

    def validate_custom_parameters(self, values):
        if any('=' not in value or not value.partition('=')[0] for value in values):
            raise serializers.ValidationError('Custom parameters must use the form key=value.')
        return values


class ReusableCreateInputSerializer(StrictSerializer):
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True, default='')
    version = serializers.ChoiceField(choices=(ReusableLtiConfiguration.LTI_1P1, ReusableLtiConfiguration.LTI_1P3))
    scope = ReusableScopeInputSerializer()
    lti_1p1 = ReusableLti11InputSerializer(required=False)
    lti_1p3 = ReusableLti13InputSerializer(required=False)
    services = ReusableServicesInputSerializer(required=False, default=dict)
    defaults = ReusableDefaultsInputSerializer(required=False, default=dict)

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('A non-empty name is required.')
        return value

    def validate(self, attrs):
        version = attrs['version']
        expected = 'lti_1p1' if version == ReusableLtiConfiguration.LTI_1P1 else 'lti_1p3'
        other = 'lti_1p3' if expected == 'lti_1p1' else 'lti_1p1'
        if expected not in attrs or other in attrs:
            raise serializers.ValidationError({expected: 'Connection settings must match the selected version.'})

        services = attrs.setdefault('services', {})
        services.setdefault('deep_linking_enabled', False)
        services.setdefault('ags_mode', 'declarative')
        services.setdefault('nrps_enabled', False)
        attrs.setdefault('defaults', {})
        if services['deep_linking_enabled'] and not services.get('deep_linking_launch_url'):
            raise serializers.ValidationError({
                'services': {'deep_linking_launch_url': 'Required when Deep Linking is enabled.'}
            })
        if expected == 'lti_1p3':
            connection = attrs[expected]
            redirects = connection['redirect_uris'] or [connection['launch_url']]
            if services.get('deep_linking_launch_url') and services['deep_linking_enabled']:
                redirects = redirects + [services['deep_linking_launch_url']]
            if any(not url for url in redirects):
                raise serializers.ValidationError({expected: {'redirect_uris': 'A valid redirect URI is required.'}})
        return attrs


class ReusableScopeAdditionInputSerializer(StrictSerializer):
    """Accept only additive grants; omitted fields never imply scope removal."""

    course_keys = serializers.ListField(child=CourseKeyStringField(allow_blank=False), required=False, default=list)
    organization_keys = serializers.ListField(
        child=serializers.CharField(allow_blank=False), required=False, default=list
    )
    site_wide = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        attrs['course_keys'] = list(dict.fromkeys(key.strip() for key in attrs.get('course_keys', [])))
        attrs['organization_keys'] = list(dict.fromkeys(
            key.strip().lower() for key in attrs.get('organization_keys', [])
        ))
        if any(not key for key in (*attrs['course_keys'], *attrs['organization_keys'])):
            raise serializers.ValidationError('Scope grants must be non-empty strings.')
        existing = self.context.get('existing_organization_keys', set())
        additions = set(attrs['organization_keys']) - existing
        if additions:
            registered = {}
            for organization in compat.get_active_organizations():
                short_name = organization.get('short_name')
                if isinstance(short_name, str):
                    registered.setdefault(short_name.lower(), set()).add(short_name)
            if any(len(registered.get(key, ())) != 1 for key in additions):
                raise serializers.ValidationError({
                    'organization_keys': ['New grants must match one unambiguous active registered organization.']
                })
        return attrs


class ReusableLti11UpdateInputSerializer(StrictSerializer):
    """Accept editable LTI 1.1 connection settings, but not credentials."""

    launch_url = HttpUrlField(max_length=255, required=False)


class ReusableLti13UpdateInputSerializer(StrictSerializer):
    """Accept editable LTI 1.3 tool settings, but not registration identity."""

    launch_url = HttpUrlField(max_length=255, required=False)
    oidc_url = HttpUrlField(max_length=255, required=False)
    redirect_uris = serializers.ListField(child=HttpUrlField(), required=False)
    tool_key_mode = serializers.ChoiceField(choices=('public_key', 'keyset_url'), required=False)
    tool_public_key = serializers.CharField(required=False, allow_blank=False)
    tool_keyset_url = HttpUrlField(max_length=255, required=False)


class ReusableUpdateInputSerializer(StrictSerializer):
    """Validate editable metadata and versioned settings without identity writes."""

    name = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    scope = ReusableScopeAdditionInputSerializer(required=False)
    lti_1p1 = ReusableLti11UpdateInputSerializer(required=False)
    lti_1p3 = ReusableLti13UpdateInputSerializer(required=False)
    services = ReusableServicesInputSerializer(required=False)
    defaults = ReusableDefaultsInputSerializer(required=False)

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('A non-empty name is required.')
        return value

    def validate(self, attrs):
        configuration = self.context['configuration']
        is_lti13 = configuration.version == ReusableLtiConfiguration.LTI_1P3
        connection_name = 'lti_1p3' if is_lti13 else 'lti_1p1'
        other_connection_name = 'lti_1p1' if is_lti13 else 'lti_1p3'
        if other_connection_name in attrs:
            raise serializers.ValidationError({
                other_connection_name: 'Connection settings must match the configuration version.'
            })

        connection = attrs.get(connection_name, {})
        connection_fields = self.fields[connection_name].fields
        launch_field = 'lti_1p3_launch_url' if is_lti13 else 'lti_1p1_launch_url'
        launch_url = connection_fields['launch_url'].run_validation(
            connection.get('launch_url', getattr(configuration, launch_field))
        )
        if is_lti13:
            try:
                connection_fields['oidc_url'].run_validation(
                    connection.get('oidc_url', configuration.lti_1p3_oidc_url)
                )
            except serializers.ValidationError as err:
                raise serializers.ValidationError({connection_name: {'oidc_url': err.detail}}) from err

            redirects = connection.get('redirect_uris', configuration.lti_1p3_redirect_uris)
            redirects = choose_lti_1p3_redirect_uris(
                redirects, launch_url, attrs.get('services', {}).get(
                    'deep_linking_launch_url', configuration.lti_advantage_deep_linking_launch_url,
                )
            )
            try:
                redirects = connection_fields['redirect_uris'].run_validation(redirects)
            except serializers.ValidationError as err:
                raise serializers.ValidationError({connection_name: {'redirect_uris': err.detail}}) from err
            if 'redirect_uris' in connection:
                connection['redirect_uris'] = redirects

            passport = configuration.lti_1p3_passport
            try:
                mode = connection_fields['tool_key_mode'].run_validation(
                    connection.get('tool_key_mode', configuration.lti_1p3_tool_key_mode)
                )
            except serializers.ValidationError as err:
                raise serializers.ValidationError({connection_name: {'tool_key_mode': err.detail}}) from err

            if mode == 'public_key':
                if 'tool_keyset_url' in connection:
                    raise serializers.ValidationError({
                        connection_name: {'tool_keyset_url': 'Not accepted in public-key mode.'}
                    })
                try:
                    public_key = connection_fields['tool_public_key'].run_validation(
                        connection.get('tool_public_key', passport.lti_1p3_tool_public_key)
                    )
                except serializers.ValidationError as err:
                    raise serializers.ValidationError({connection_name: {'tool_public_key': err.detail}}) from err
                if not public_key.strip() or 'PRIVATE KEY' in public_key:
                    raise serializers.ValidationError({
                        connection_name: {'tool_public_key': 'A public key is required; private keys are not accepted.'}
                    })
            else:
                if 'tool_public_key' in connection:
                    raise serializers.ValidationError({
                        connection_name: {'tool_public_key': 'Not accepted in keyset URL mode.'}
                    })
                try:
                    tool_keyset_url = connection_fields['tool_keyset_url'].run_validation(
                        connection.get('tool_keyset_url', passport.lti_1p3_tool_keyset_url)
                    )
                except serializers.ValidationError as err:
                    raise serializers.ValidationError({connection_name: {'tool_keyset_url': err.detail}}) from err
                if not tool_keyset_url:
                    raise serializers.ValidationError({
                        connection_name: {'tool_keyset_url': 'Required in keyset URL mode.'}
                    })

        services = {
            'deep_linking_enabled': configuration.lti_advantage_deep_linking_enabled,
            'deep_linking_launch_url': configuration.lti_advantage_deep_linking_launch_url,
            'ags_mode': configuration.lti_advantage_ags_mode,
            'nrps_enabled': configuration.lti_advantage_enable_nrps,
        }
        services.update(attrs.get('services', {}))
        validated_services = ReusableServicesInputSerializer(data=services)
        validated_services.is_valid(raise_exception=True)
        if validated_services.validated_data['deep_linking_enabled'] and not validated_services.validated_data.get(
            'deep_linking_launch_url'
        ):
            raise serializers.ValidationError({
                'services': {'deep_linking_launch_url': 'Required when Deep Linking is enabled.'}
            })
        return attrs


class ReusableListSerializer(serializers.Serializer):
    """Allowlisted metadata safe for any user authorized to see a configuration."""

    config_id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    version = serializers.CharField(read_only=True)
    scope_summary = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    can_manage = serializers.SerializerMethodField()
    deep_linking_enabled = serializers.BooleanField(source='lti_advantage_deep_linking_enabled', read_only=True)
    ags_mode = serializers.CharField(source='lti_advantage_ags_mode', read_only=True)
    nrps_enabled = serializers.BooleanField(source='lti_advantage_enable_nrps', read_only=True)

    def get_scope_summary(self, obj):
        return {
            'site_wide': obj.site_wide,
            'course_count': obj.course_grants.count(),
            'organization_count': obj.organization_grants.count(),
        }

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
    scope = serializers.SerializerMethodField()
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

    def get_scope(self, obj):
        result = {'site_wide': obj.site_wide}
        if self.get_can_manage(obj):
            result.update(
                course_keys=[str(key) for key in obj.course_grants.values_list('course_key', flat=True)],
                organization_keys=list(obj.organization_grants.values_list('organization', flat=True)),
            )
        else:
            result['summary'] = self.get_scope_summary(obj)
        return result

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
