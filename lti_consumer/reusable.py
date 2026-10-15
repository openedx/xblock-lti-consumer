"""Atomic creation of complete reusable LTI configurations.

This module accepts an already-validated request-shaped mapping. It performs only
service-boundary invariant checks and persistence; authorization, full field
validation, updates, and serialization belong to their respective layers.
"""

import secrets
import uuid
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils.translation import gettext_lazy as _
from opaque_keys import InvalidKeyError
from opaque_keys.edx.locator import CourseLocator

from lti_consumer.models import Lti1p3Passport, ReusableLtiConfiguration
from lti_consumer.plugin import compat
from lti_consumer.plugin.reusable_keys import normalize_course_key


@dataclass(frozen=True)
class ReusableCreationResult:
    """Created row plus the one-time credentials, when this is an LTI 1.1 config."""

    configuration: ReusableLtiConfiguration
    one_time_credentials: dict | None = None


_REUSABLE_SERVICE_FIELDS = {
    'deep_linking_enabled': 'lti_advantage_deep_linking_enabled',
    'deep_linking_launch_url': 'lti_advantage_deep_linking_launch_url',
    'ags_mode': 'lti_advantage_ags_mode',
    'nrps_enabled': 'lti_advantage_enable_nrps',
}


def service_configuration_values(services):
    """Map provided service settings to model fields, normalizing nullable URLs."""
    return {
        field: '' if key == 'deep_linking_launch_url' and services[key] is None else services[key]
        for key, field in _REUSABLE_SERVICE_FIELDS.items() if key in services
    }


def _invalid(message):
    """Raise a field-independent validation error."""
    raise ValidationError(message)


def _is_nonblank_string(value):
    """Return whether a value is a non-empty string after trimming."""
    return isinstance(value, str) and bool(value.strip())


_CONTEXT_TYPES = ('course', 'organization', 'site')


def _unambiguous_active_organization_keys():
    """Return normalized keys for unique, active organization short names."""
    registered = {}
    for organization in compat.get_active_organizations():
        short_name = organization.get('short_name')
        if isinstance(short_name, str):
            registered.setdefault(short_name.lower(), set()).add(short_name)
    return {key for key, names in registered.items() if len(names) == 1}


def validate_reusable_context(context):
    """Validate and normalize one create-only context.

    Returns ``{'type': 'site'}`` or ``{'type': ..., 'key': ...}`` with the
    course key canonicalized and the organization key lowercased. Raises
    ``ValidationError`` for invalid shape, content, or organization lookups.
    """
    if not isinstance(context, dict):
        _invalid(_('A context with a type of course, organization, or site is required.'))
    if set(context) - {'type', 'key'}:
        _invalid(_('The context must contain only type and key.'))

    context_type = context.get('type')
    if context_type not in _CONTEXT_TYPES:
        _invalid(_('A context type of course, organization, or site is required.'))
    if context_type == 'site':
        if 'key' in context:
            _invalid(_('The site context must not include a key.'))
        return {'type': 'site'}

    key = context.get('key')
    if not _is_nonblank_string(key):
        _invalid(_('A context key is required for course and organization contexts.'))
    key = key.strip()
    max_length = ReusableLtiConfiguration._meta.get_field('context_key').max_length

    if context_type == 'course':
        try:
            course_key = normalize_course_key(key)
        except (InvalidKeyError, TypeError, ValueError):
            _invalid(_('Invalid course key.'))
        if not isinstance(course_key, CourseLocator):
            _invalid(_('Invalid course key.'))
        course_key = str(course_key)
        if len(course_key) > max_length:
            _invalid(_('The context key is too long.'))
        return {'type': 'course', 'key': course_key}

    key = key.lower()
    if len(key) > max_length:
        _invalid(_('The context key is too long.'))
    if key not in _unambiguous_active_organization_keys():
        _invalid(_('Organization must match one unambiguous active registered organization.'))
    return {'type': 'organization', 'key': key}


def _validate_lti_1p1(section):
    """Validate LTI 1.1 connection and optional credentials."""
    if not _is_nonblank_string(section.get('launch_url')):
        _invalid(_('A launch URL is required.'))
    for key in ('client_key', 'client_secret'):
        value = section.get(key)
        if value is not None and not _is_nonblank_string(value):
            _invalid(_('Credential overrides must be non-empty strings.'))


def _validate_lti_1p3(section):
    """Validate LTI 1.3 connection, identity overrides, and tool-key mode."""
    if not _is_nonblank_string(section.get('launch_url')):
        _invalid(_('A launch URL is required.'))
    if not _is_nonblank_string(section.get('oidc_url')):
        _invalid(_('An OIDC URL is required.'))

    mode = section.get('tool_key_mode')
    if mode == 'public_key':
        has_material = _is_nonblank_string(section.get('tool_public_key'))
        if not has_material or section.get('tool_keyset_url'):
            _invalid(_('The LTI 1.3 public-key mode requires only a tool public key.'))
    elif mode == 'keyset_url':
        has_material = _is_nonblank_string(section.get('tool_keyset_url'))
        if not has_material or section.get('tool_public_key'):
            _invalid(_('The LTI 1.3 keyset mode requires only a tool keyset URL.'))
    else:
        _invalid(_('A supported LTI 1.3 tool-key mode and material are required.'))

    for key in ('client_id', 'deployment_id'):
        value = section.get(key)
        if value is not None and not _is_nonblank_string(value):
            _invalid(_('Registration identity overrides must be non-empty strings.'))

    redirects = section.get('redirect_uris', [])
    if not isinstance(redirects, (list, tuple)):
        _invalid(_('Redirect URIs must be a list.'))
    if any(not _is_nonblank_string(uri) for uri in redirects):
        _invalid(_('Redirect URIs must be non-empty strings.'))


def _validate_input(data):
    """Validate service-boundary consistency for already-validated input.

    Example::

        {
            'name': 'Tool',
            'version': 'lti_1p1',
            'context': {'type': 'course', 'key': 'course-v1:Org+Course+Run'},
            'lti_1p1': {'launch_url': 'https://tool.example/launch'},
        }
    """
    if not isinstance(data, dict):
        _invalid(_('Invalid reusable configuration.'))

    version = data.get('version')
    if version not in (ReusableLtiConfiguration.LTI_1P1, ReusableLtiConfiguration.LTI_1P3):
        _invalid(_('A supported LTI version is required.'))

    section = data.get(version)
    other_sections = (ReusableLtiConfiguration.LTI_1P1, ReusableLtiConfiguration.LTI_1P3)
    if not isinstance(section, dict) or any(key in data for key in other_sections if key != version):
        _invalid(_('The connection settings must match the selected LTI version.'))

    name = data.get('name')
    if not _is_nonblank_string(name):
        _invalid(_('A non-empty name is required.'))
    if len(name.strip()) > ReusableLtiConfiguration._meta.get_field('name').max_length:
        _invalid(_('The name is too long.'))

    context = validate_reusable_context(data.get('context'))
    if version == ReusableLtiConfiguration.LTI_1P1:
        _validate_lti_1p1(section)
    else:
        _validate_lti_1p3(section)

    return name.strip(), version, section, context


def create_reusable_configuration(validated_data):
    """Persist a complete reusable configuration and its single context in one transaction.

    ``validated_data`` must be a mapping in the CMS create-request shape after
    API validation (``name``, ``version``, ``context``, and exactly one version
    section, optionally ``services`` and ``defaults``). Authorization and full
    URL/schema validation are intentionally not performed here. Essential
    version, connection, identity-material, and context invariants are checked
    again before any write. Returns ``ReusableCreationResult``; its
    ``one_time_credentials`` is populated only for LTI 1.1.
    """
    name, version, section, context = _validate_input(validated_data)
    services = validated_data.get('services') or {}
    defaults = validated_data.get('defaults') or {}
    if not isinstance(services, dict) or not isinstance(defaults, dict):
        _invalid(_('Invalid reusable configuration settings.'))

    credentials = None
    config_values = {
        'name': name,
        'description': validated_data.get('description') or '',
        'version': version,
        'context_type': context['type'],
        'context_key': context.get('key', ''),
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

    default_fields = (
        'display_name',
        'enable_grading',
        'grade_weight',
        'accept_grades_after_due_date',
        'open_tool_in',
        'inline_height',
        'modal_height',
        'modal_width',
        'launch_button_text',
        'send_extra_parameters',
        'custom_parameters',
    )
    config_values.update(service_configuration_values(services))
    config_values.update({field: defaults[field] for field in default_fields if field in defaults})

    try:
        with transaction.atomic():
            if version == ReusableLtiConfiguration.LTI_1P3:
                # Best-effort cross-table collision check: legacy passport writes
                # do not share a database uniqueness constraint with this table.
                if Lti1p3Passport.objects.filter(lti_1p3_client_id=client_id).exists():
                    _invalid(_('The requested configuration conflicts with an existing identity.'))
                passport_values = {
                    'name': name,
                    'lti_1p3_client_id': client_id,
                    'lti_1p3_tool_public_key': section.get('tool_public_key', '') or '',
                    'lti_1p3_tool_keyset_url': section.get('tool_keyset_url', '') or '',
                }
                passport = Lti1p3Passport.objects.create(**passport_values)
                # Ensure the platform RSA key and JWK exist before committing.
                passport.generate_lti_1p3_keys_if_missing()
                config_values['lti_1p3_passport'] = passport

            configuration = ReusableLtiConfiguration.objects.create(**config_values)
    except IntegrityError:
        # Translate only after atomic has rolled back and the connection is usable.
        raise ValidationError(_('A reusable configuration conflicts with an existing record.')) from None

    return ReusableCreationResult(configuration=configuration, one_time_credentials=credentials)
