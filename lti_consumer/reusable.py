"""Atomic creation of complete reusable LTI configurations.

This module accepts an already-validated request-shaped mapping. It performs only
service-boundary invariant checks and persistence; authorization, full field
validation, organization-registry validation, updates, and serialization belong
to their respective layers.
"""

from dataclasses import dataclass
import secrets
import uuid

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from lti_consumer.models import (
    Lti1p3Passport,
    ReusableLtiConfiguration,
    ReusableLtiConfigurationCourse,
    ReusableLtiConfigurationOrganization,
)


@dataclass(frozen=True)
class ReusableCreationResult:
    """Created row plus the one-time credentials, when this is an LTI 1.1 config."""

    configuration: ReusableLtiConfiguration
    one_time_credentials: dict | None = None


def _invalid(message):
    """Raise a field-independent validation error."""
    raise ValidationError(message)


def _validate_input(data):  # pylint: disable=too-many-statements
    """Check service-boundary consistency for already-validated input."""
    if not isinstance(data, dict):
        _invalid('Invalid reusable configuration.')

    version = data.get('version')
    if version not in (ReusableLtiConfiguration.LTI_1P1, ReusableLtiConfiguration.LTI_1P3):
        _invalid('A supported LTI version is required.')
    expected_section = version
    other_section = 'lti_1p3' if version == 'lti_1p1' else 'lti_1p1'
    section = data.get(expected_section)
    if not isinstance(section, dict) or other_section in data:
        _invalid('The connection settings must match the selected LTI version.')

    name = data.get('name')
    if not isinstance(name, str) or not name.strip():
        _invalid('A non-empty name is required.')
    if len(name.strip()) > ReusableLtiConfiguration._meta.get_field('name').max_length:
        _invalid('The name is too long.')

    scope = data.get('scope')
    if not isinstance(scope, dict):
        _invalid('At least one scope grant is required.')
    course_keys = scope.get('course_keys', [])
    organization_keys = scope.get('organization_keys', [])
    site_wide = scope.get('site_wide', False)
    if not isinstance(course_keys, (list, tuple)) or not isinstance(organization_keys, (list, tuple)):
        _invalid('Scope grants must be lists.')
    if not isinstance(site_wide, bool) or not (course_keys or organization_keys or site_wide):
        _invalid('At least one scope grant is required.')
    if any(not isinstance(value, str) or not value.strip() for value in (*course_keys, *organization_keys)):
        _invalid('Scope grants must be non-empty strings.')

    launch_url = section.get('launch_url')
    if not isinstance(launch_url, str) or not launch_url.strip():
        _invalid('A launch URL is required.')
    if version == ReusableLtiConfiguration.LTI_1P1:
        for key in ('client_key', 'client_secret'):
            value = section.get(key)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                _invalid('Credential overrides must be non-empty strings.')
    else:
        if not isinstance(section.get('oidc_url'), str) or not section['oidc_url'].strip():
            _invalid('An OIDC URL is required.')
        mode = section.get('tool_key_mode')
        if mode == 'public_key':
            has_material = isinstance(section.get('tool_public_key'), str) and bool(section['tool_public_key'].strip())
            if not has_material or section.get('tool_keyset_url'):
                _invalid('The LTI 1.3 public-key mode requires only a tool public key.')
        elif mode == 'keyset_url':
            has_material = isinstance(section.get('tool_keyset_url'), str) and bool(section['tool_keyset_url'].strip())
            if not has_material or section.get('tool_public_key'):
                _invalid('The LTI 1.3 keyset mode requires only a tool keyset URL.')
        else:
            _invalid('A supported LTI 1.3 tool-key mode and material are required.')
        for key in ('client_id', 'deployment_id'):
            value = section.get(key)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                _invalid('Registration identity overrides must be non-empty strings.')
        redirects = section.get('redirect_uris', [])
        if not isinstance(redirects, (list, tuple)):
            _invalid('Redirect URIs must be a list.')
        if any(not isinstance(uri, str) or not uri.strip() for uri in redirects):
            _invalid('Redirect URIs must be non-empty strings.')

    return (
        name.strip(),
        version,
        section,
        list(dict.fromkeys(course_keys)),
        list(dict.fromkeys(key.lower() for key in organization_keys)),
        site_wide,
    )


def create_reusable_configuration(validated_data):
    """Persist a complete reusable configuration and grants in one transaction.

    ``validated_data`` must be a mapping in the CMS create-request shape after
    API validation (``name``, ``version``, ``scope``, and exactly one version
    section, optionally ``services`` and ``defaults``). Authorization and full
    URL/schema validation are intentionally not performed here. Essential
    version, connection, identity-material, and nonempty-scope invariants are
    checked again before any write. Returns ``ReusableCreationResult``; its
    ``one_time_credentials`` is populated only for LTI 1.1.
    """
    name, version, section, course_keys, organization_keys, site_wide = _validate_input(validated_data)
    services = validated_data.get('services') or {}
    defaults = validated_data.get('defaults') or {}
    if not isinstance(services, dict) or not isinstance(defaults, dict):
        _invalid('Invalid reusable configuration settings.')

    credentials = None
    passport = None
    config_values = {
        'name': name,
        'description': validated_data.get('description') or '',
        'version': version,
        'site_wide': site_wide,
    }
    if version == ReusableLtiConfiguration.LTI_1P1:
        client_key = section.get('client_key') or secrets.token_urlsafe(32)
        client_secret = section.get('client_secret') or secrets.token_urlsafe(32)
        config_values.update(
            lti_1p1_launch_url=section['launch_url'],
            lti_1p1_client_key=client_key,
            lti_1p1_client_secret=client_secret,
        )
        credentials = {'client_key': client_key, 'client_secret': client_secret}
    else:
        client_id = section.get('client_id') or str(uuid.uuid4())
        deployment_id = section.get('deployment_id') or str(uuid.uuid4())
        config_values.update(
            lti_1p3_launch_url=section['launch_url'],
            lti_1p3_oidc_url=section['oidc_url'],
            lti_1p3_redirect_uris=list(section.get('redirect_uris') or []),
            lti_1p3_client_id=client_id,
            lti_1p3_deployment_id=deployment_id,
            lti_1p3_tool_key_mode=section['tool_key_mode'],
        )

    service_fields = {
        'deep_linking_enabled': 'lti_advantage_deep_linking_enabled',
        'deep_linking_launch_url': 'lti_advantage_deep_linking_launch_url',
        'ags_mode': 'lti_advantage_ags_mode',
        'nrps_enabled': 'lti_advantage_enable_nrps',
    }
    default_fields = {
        'display_name': 'display_name',
        'enable_grading': 'enable_grading',
        'grade_weight': 'grade_weight',
        'accept_grades_after_due_date': 'accept_grades_after_due_date',
        'open_tool_in': 'open_tool_in',
        'inline_height': 'inline_height',
        'modal_height': 'modal_height',
        'modal_width': 'modal_width',
        'launch_button_text': 'launch_button_text',
        'send_extra_parameters': 'send_extra_parameters',
        'custom_parameters': 'custom_parameters',
    }
    config_values.update({field: services[key] for key, field in service_fields.items() if key in services})
    config_values.update({field: defaults[key] for key, field in default_fields.items() if key in defaults})

    try:
        with transaction.atomic():
            if version == ReusableLtiConfiguration.LTI_1P3:
                # Best-effort cross-table collision check: legacy passport writes
                # do not share a database uniqueness constraint with this table.
                if Lti1p3Passport.objects.filter(lti_1p3_client_id=client_id).exists():
                    _invalid('The requested configuration conflicts with an existing identity.')
                passport_values = {
                    'name': name,
                    'lti_1p3_client_id': client_id,
                    'lti_1p3_tool_public_key': section.get('tool_public_key', '') or '',
                    'lti_1p3_tool_keyset_url': section.get('tool_keyset_url', '') or '',
                }
                passport = Lti1p3Passport.objects.create(**passport_values)
                # Call the generator method, never its lazy read properties.
                passport._generate_lti_1p3_keys_if_missing()  # pylint: disable=protected-access
                config_values['lti_1p3_passport'] = passport

            configuration = ReusableLtiConfiguration.objects.create(**config_values)
            ReusableLtiConfigurationCourse.objects.bulk_create([
                ReusableLtiConfigurationCourse(configuration=configuration, course_key=key)
                for key in course_keys
            ])
            ReusableLtiConfigurationOrganization.objects.bulk_create([
                ReusableLtiConfigurationOrganization(configuration=configuration, organization=key.lower())
                for key in organization_keys
            ])
    except IntegrityError:
        # Translate only after atomic has rolled back and the connection is usable.
        raise ValidationError('A reusable configuration conflicts with an existing record.') from None

    return ReusableCreationResult(configuration=configuration, one_time_credentials=credentials)
