"""Atomic creation and update of complete reusable LTI configurations.

These two functions are the only write entry points for
ReusableLtiConfiguration. They own semantic validation, Creation Context
policy invocation, target lookup, authorization ordering, the transaction, the
update row lock, configuration writes, and conflict interpretation. Adapters
supply parsed wire mappings; unknown members are refused here as well so a
non-HTTP caller cannot smuggle one in.
"""

import secrets
import uuid
from dataclasses import dataclass
from math import isfinite
from typing import NamedTuple

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import URLValidator
from django.db import IntegrityError, transaction
from django.utils.translation import gettext_lazy as _

from lti_consumer.exceptions import ReusableConfigurationError
from lti_consumer.models import ReusableLtiConfiguration
from lti_consumer.reusable_context import CreationContextPolicy

LTI_1P1 = ReusableLtiConfiguration.LTI_1P1
LTI_1P3 = ReusableLtiConfiguration.LTI_1P3

_NAME_MAX_LENGTH = ReusableLtiConfiguration._meta.get_field('name').max_length
_LAUNCH_URL_MAX_LENGTH = ReusableLtiConfiguration._meta.get_field('lti_1p1_launch_url').max_length
_OIDC_URL_MAX_LENGTH = ReusableLtiConfiguration._meta.get_field('lti_1p3_oidc_url').max_length
_CREDENTIAL_MAX_LENGTH = ReusableLtiConfiguration._meta.get_field('lti_1p1_client_key').max_length
_IDENTITY_MAX_LENGTH = ReusableLtiConfiguration._meta.get_field('lti_1p3_client_id').max_length
_KEYSET_URL_MAX_LENGTH = ReusableLtiConfiguration._meta.get_field('lti_1p3_tool_keyset_url').max_length
_DEEP_LINKING_URL_MAX_LENGTH = ReusableLtiConfiguration._meta.get_field(
    'lti_advantage_deep_linking_launch_url',
).max_length
_DISPLAY_NAME_MAX_LENGTH = ReusableLtiConfiguration._meta.get_field('display_name').max_length
_LAUNCH_BUTTON_TEXT_MAX_LENGTH = ReusableLtiConfiguration._meta.get_field('launch_button_text').max_length

_URL_VALIDATOR = URLValidator(schemes=('http', 'https'))
_AGS_MODES = ('disabled', 'declarative', 'programmatic')
_OPEN_TOOL_IN_MODES = ('iframe', 'modal', 'new_window')
_TOOL_KEY_MODES = ('public_key', 'keyset_url')

_CREATE_MEMBERS = {'name', 'description', 'version', 'context', 'lti_1p1', 'lti_1p3', 'services', 'defaults'}
_UPDATE_MEMBERS = {'name', 'description', 'version', 'lti_1p1', 'lti_1p3', 'services', 'defaults'}
_CONNECTION_MEMBERS = {
    LTI_1P1: {'launch_url', 'client_key', 'client_secret'},
    LTI_1P3: {
        'launch_url', 'oidc_url', 'redirect_uris', 'tool_key_mode', 'tool_public_key', 'tool_keyset_url',
        'client_id', 'deployment_id',
    },
}
_UPDATE_CONNECTION_MEMBERS = {
    LTI_1P1: {'launch_url'},
    LTI_1P3: {'launch_url', 'oidc_url', 'redirect_uris', 'tool_key_mode', 'tool_public_key', 'tool_keyset_url'},
}
_SERVICE_MEMBERS = {'deep_linking_enabled', 'deep_linking_launch_url', 'ags_mode', 'nrps_enabled'}
_DEFAULT_MEMBERS = {
    'display_name', 'enable_grading', 'grade_weight', 'accept_grades_after_due_date', 'open_tool_in',
    'inline_height', 'modal_height', 'modal_width', 'launch_button_text', 'send_extra_parameters',
    'custom_parameters',
}
_REUSABLE_SERVICE_FIELDS = {
    'deep_linking_enabled': 'lti_advantage_deep_linking_enabled',
    'deep_linking_launch_url': 'lti_advantage_deep_linking_launch_url',
    'ags_mode': 'lti_advantage_ags_mode',
    'nrps_enabled': 'lti_advantage_enable_nrps',
}


@dataclass(frozen=True)
class ReusableCreationResult:
    """Created row plus the one-time credentials, when this is an LTI 1.1 config."""

    configuration: ReusableLtiConfiguration
    one_time_credentials: dict | None = None


def service_configuration_values(services):
    """Map provided service settings to model fields, normalizing nullable URLs."""
    return {
        field: '' if key == 'deep_linking_launch_url' and services[key] is None else services[key]
        for key, field in _REUSABLE_SERVICE_FIELDS.items() if key in services
    }


def _invalid(field, message):
    """Raise an invalid-category error addressed to one member."""
    raise ReusableConfigurationError('invalid', message, field=field)


def _conflict(message):
    """Raise a conflict-category error with no member address."""
    raise ReusableConfigurationError('conflict', message) from None


def _reject_unknown(members, allowed, prefix=''):
    """Refuse the first unknown member of a parsed wire mapping."""
    if not isinstance(members, dict):
        return
    unknown = sorted(set(members) - set(allowed))
    if unknown:
        _invalid(f'{prefix}{unknown[0]}', _('Unknown field.'))


def _nonblank_string(value, field, max_length=None):
    """Return the trimmed string, or raise an addressed invalid error."""
    if not isinstance(value, str) or not value.strip():
        _invalid(field, _('A non-empty string is required.'))
    return _checked_length(value.strip(), field, max_length)


def _optional_string(value, field, max_length=None):
    """Accept a string or None, treating None as blank, and trim it."""
    if value is None:
        value = ''
    if not isinstance(value, str):
        _invalid(field, _('A string is required.'))
    return _checked_length(value.strip(), field, max_length)


def _checked_length(value, field, max_length):
    """Raise when a normalized value exceeds its stored length."""
    if max_length is not None and len(value) > max_length:
        _invalid(field, _('This value is too long.'))
    return value


def _http_url(value, field, max_length=None):
    """Return a trimmed HTTP(S) URL, or raise an addressed invalid error."""
    value = _nonblank_string(value, field, max_length)
    try:
        _URL_VALIDATOR(value)
    except DjangoValidationError:
        _invalid(field, _('Enter a valid HTTP(S) URL.'))
    return value


def _http_url_list(value, field):
    """Return a list of trimmed HTTP(S) URLs, or raise an addressed invalid error."""
    if not isinstance(value, (list, tuple)):
        _invalid(field, _('A list of URLs is required.'))
    return [_http_url(item, field) for item in value]


def _checked_bool(value, field):
    """Return a boolean, or raise an addressed invalid error."""
    if not isinstance(value, bool):
        _invalid(field, _('A boolean is required.'))
    return value


def _checked_int(value, field, minimum, maximum):
    """Return an integer within its range, or raise an addressed invalid error."""
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        _invalid(field, _('An integer within the supported range is required.'))
    return value


def _checked_number(value, field, minimum):
    """Return a finite number at or above its minimum, or raise an addressed invalid error."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < minimum:
        _invalid(field, _('A finite number within the supported range is required.'))
    return value


def _public_key(value, field):
    """Return tool key material that is public, or raise an addressed invalid error."""
    value = _nonblank_string(value, field)
    if 'PRIVATE KEY' in value:
        _invalid(field, _('Private keys are not accepted.'))
    return value


def _custom_parameters(value):
    """Validate key=value custom parameters and return them trimmed."""
    if not isinstance(value, (list, tuple)):
        _invalid('defaults.custom_parameters', _('A list is required.'))
    parameters = []
    for item in value:
        parameter = _nonblank_string(item, 'defaults.custom_parameters')
        if '=' not in parameter or not parameter.partition('=')[0]:
            _invalid('defaults.custom_parameters', _('Custom parameters must use the form key=value.'))
        parameters.append(parameter)
    return parameters


def _validated_services(services):
    """Validate service settings and return them with normalized URLs."""
    if not isinstance(services, dict):
        _invalid('services', _('Invalid reusable configuration settings.'))
    _reject_unknown(services, _SERVICE_MEMBERS, prefix='services.')
    validated = dict(services)
    for key in ('deep_linking_enabled', 'nrps_enabled'):
        if key in validated:
            validated[key] = _checked_bool(validated[key], f'services.{key}')
    if 'ags_mode' in validated and validated['ags_mode'] not in _AGS_MODES:
        _invalid('services.ags_mode', _('A supported AGS mode is required.'))
    if 'deep_linking_launch_url' in validated:
        launch_url = validated['deep_linking_launch_url']
        validated['deep_linking_launch_url'] = (
            ''
            if launch_url is None or launch_url == ''
            else _http_url(launch_url, 'services.deep_linking_launch_url', _DEEP_LINKING_URL_MAX_LENGTH)
        )
    if validated.get('deep_linking_enabled') and not validated.get('deep_linking_launch_url'):
        _invalid('services.deep_linking_launch_url', _('Deep Linking requires an explicit launch URL.'))
    return validated


def _validated_defaults(defaults):
    """Validate provided placement defaults and return them normalized."""
    if not isinstance(defaults, dict):
        _invalid('defaults', _('Invalid reusable configuration settings.'))
    _reject_unknown(defaults, _DEFAULT_MEMBERS, prefix='defaults.')
    validated = dict(defaults)
    if 'display_name' in validated:
        validated['display_name'] = _nonblank_string(
            validated['display_name'], 'defaults.display_name', _DISPLAY_NAME_MAX_LENGTH,
        )
    for key in ('enable_grading', 'accept_grades_after_due_date', 'send_extra_parameters'):
        if key in validated:
            validated[key] = _checked_bool(validated[key], f'defaults.{key}')
    if 'grade_weight' in validated:
        validated['grade_weight'] = _checked_number(validated['grade_weight'], 'defaults.grade_weight', 0)
    if 'open_tool_in' in validated and validated['open_tool_in'] not in _OPEN_TOOL_IN_MODES:
        _invalid('defaults.open_tool_in', _('A supported open-tool mode is required.'))
    if 'inline_height' in validated:
        validated['inline_height'] = _checked_int(validated['inline_height'], 'defaults.inline_height', 0, 2147483647)
    for key in ('modal_height', 'modal_width'):
        if key in validated:
            validated[key] = _checked_int(validated[key], f'defaults.{key}', 0, 100)
    if 'launch_button_text' in validated:
        validated['launch_button_text'] = _optional_string(
            validated['launch_button_text'], 'defaults.launch_button_text', _LAUNCH_BUTTON_TEXT_MAX_LENGTH,
        )
    if 'custom_parameters' in validated:
        validated['custom_parameters'] = _custom_parameters(validated['custom_parameters'])
    return validated


def _validated_lti_1p1_create(section):
    """Validate LTI 1.1 creation settings and return them normalized."""
    validated = {
        'launch_url': _http_url(section.get('launch_url'), 'lti_1p1.launch_url', _LAUNCH_URL_MAX_LENGTH),
    }
    for key in ('client_key', 'client_secret'):
        if key in section:
            validated[key] = _nonblank_string(section[key], f'lti_1p1.{key}', _CREDENTIAL_MAX_LENGTH)
    return validated


def _validated_lti_1p3_create(section):
    """Validate LTI 1.3 creation settings, tool-key mode included, and normalize them."""
    validated = {
        'launch_url': _http_url(section.get('launch_url'), 'lti_1p3.launch_url', _LAUNCH_URL_MAX_LENGTH),
        'oidc_url': _http_url(section.get('oidc_url'), 'lti_1p3.oidc_url', _OIDC_URL_MAX_LENGTH),
        'redirect_uris': _http_url_list(section.get('redirect_uris', []), 'lti_1p3.redirect_uris'),
    }
    mode = section.get('tool_key_mode')
    if mode not in _TOOL_KEY_MODES:
        _invalid('lti_1p3.tool_key_mode', _('A supported LTI 1.3 tool-key mode is required.'))
    validated['tool_key_mode'] = mode
    if 'tool_public_key' in section:
        validated['tool_public_key'] = _public_key(section['tool_public_key'], 'lti_1p3.tool_public_key')
    if 'tool_keyset_url' in section:
        validated['tool_keyset_url'] = _http_url(
            section['tool_keyset_url'], 'lti_1p3.tool_keyset_url', _KEYSET_URL_MAX_LENGTH,
        )
    if mode == 'public_key':
        if 'tool_keyset_url' in validated:
            _invalid('lti_1p3.tool_keyset_url', _('Not accepted in public-key mode.'))
        if not validated.get('tool_public_key'):
            _invalid('lti_1p3.tool_public_key', _('A public key is required in public-key mode.'))
    else:
        if 'tool_public_key' in validated:
            _invalid('lti_1p3.tool_public_key', _('Not accepted in keyset URL mode.'))
        if not validated.get('tool_keyset_url'):
            _invalid('lti_1p3.tool_keyset_url', _('A keyset URL is required in keyset URL mode.'))
    for key in ('client_id', 'deployment_id'):
        if key in section:
            validated[key] = _nonblank_string(section[key], f'lti_1p3.{key}', _IDENTITY_MAX_LENGTH)
    return validated


class _ValidatedCreate(NamedTuple):
    """Normalized members of one validated create mapping."""

    name: str
    version: str
    section: dict
    description: str
    services: dict
    defaults: dict


def _validated_create(data):
    """Validate a parsed create mapping and return its normalized members."""
    _reject_unknown(data, _CREATE_MEMBERS)
    name = _nonblank_string(data.get('name'), 'name', _NAME_MAX_LENGTH)
    version = data.get('version')
    if version not in (LTI_1P1, LTI_1P3):
        _invalid('version', _('A supported LTI version is required.'))
    other_version = LTI_1P3 if version == LTI_1P1 else LTI_1P1
    section = data.get(version)
    if not isinstance(section, dict) or other_version in data:
        _invalid(version, _('Connection settings must match the selected version.'))
    _reject_unknown(section, _CONNECTION_MEMBERS[version], prefix=f'{version}.')
    validated_section = (
        _validated_lti_1p1_create(section) if version == LTI_1P1 else _validated_lti_1p3_create(section)
    )

    return _ValidatedCreate(
        name=name,
        version=version,
        section=validated_section,
        description=_optional_string(data.get('description'), 'description'),
        services=_validated_services(data['services'] if 'services' in data else {}),
        defaults=_validated_defaults(data['defaults'] if 'defaults' in data else {}),
    )


def create_reusable_configuration(actor, data):
    """Create a complete reusable configuration with its single Creation Context.

    The actor authorizes the context through the Creation Context policy.
    data is a parsed wire mapping. Returns ReusableCreationResult; its
    one_time_credentials is populated only for a successful LTI 1.1 create.
    """
    if not isinstance(data, dict):
        _invalid(None, _('Invalid reusable configuration.'))

    context = CreationContextPolicy(actor).authorize_creation(data.get('context'))
    validated = _validated_create(data)
    section = validated.section

    credentials = None
    configuration_values = {
        'name': validated.name,
        'description': validated.description,
        'version': validated.version,
        'context_type': context.type,
        'context_key': context.key,
    }
    if validated.version == LTI_1P1:
        client_key = section.get('client_key') or secrets.token_urlsafe(32)
        client_secret = section.get('client_secret') or secrets.token_urlsafe(32)
        configuration_values.update(
            lti_1p1_launch_url=section['launch_url'],
            lti_1p1_client_key=client_key,
            lti_1p1_client_secret=client_secret,
            # Not an LTI 1.3 registration: bypass the model's random Client ID default.
            lti_1p3_client_id=None,
        )
        credentials = {'client_key': client_key, 'client_secret': client_secret}
    else:
        client_id = section.get('client_id') or str(uuid.uuid4())
        deployment_id = section.get('deployment_id') or str(uuid.uuid4())
        configuration_values.update(
            lti_1p3_launch_url=section['launch_url'],
            lti_1p3_oidc_url=section['oidc_url'],
            lti_1p3_redirect_uris=section['redirect_uris'],
            lti_1p3_client_id=client_id,
            lti_1p3_deployment_id=deployment_id,
            lti_1p3_tool_key_mode=section['tool_key_mode'],
        )

    configuration_values.update(service_configuration_values(validated.services))
    configuration_values.update(
        {key: validated.defaults[key] for key in _DEFAULT_MEMBERS if key in validated.defaults},
    )

    if validated.version == LTI_1P3:
        configuration_values.update(
            lti_1p3_tool_public_key=section.get('tool_public_key', ''),
            lti_1p3_tool_keyset_url=section.get('tool_keyset_url', ''),
        )

    try:
        with transaction.atomic():
            configuration = ReusableLtiConfiguration.objects.create(**configuration_values)
            if validated.version == LTI_1P3:
                # Platform RSA material is generated once, on the same row, before commit.
                configuration.generate_lti_1p3_keys_if_missing()
    except IntegrityError:
        _conflict(_('A reusable configuration conflicts with an existing record.'))

    return ReusableCreationResult(configuration=configuration, one_time_credentials=credentials)


def _locked_visible_configuration(policy, config_id):
    """Lock and return a configuration this actor can see, or raise not_found."""
    try:
        configuration = policy.visible_configurations().select_for_update().filter(passport_id=config_id).first()
    except (ValueError, DjangoValidationError):
        configuration = None
    if configuration is None:
        raise ReusableConfigurationError('not_found', _('Reusable configuration not found.'))
    return configuration


def _stored_services(configuration):
    """Return the configuration's stored service settings."""
    return {key: getattr(configuration, field) for key, field in _REUSABLE_SERVICE_FIELDS.items()}


def _apply_lti_1p1_changes(configuration, section):
    """Validate merged LTI 1.1 settings and assign them."""
    configuration.lti_1p1_launch_url = _http_url(
        section.get('launch_url', configuration.lti_1p1_launch_url), 'lti_1p1.launch_url', _LAUNCH_URL_MAX_LENGTH,
    )


def _apply_lti_1p3_changes(configuration, section):
    """Validate merged LTI 1.3 settings and assign them to the configuration row."""
    launch_url = _http_url(
        section.get('launch_url', configuration.lti_1p3_launch_url), 'lti_1p3.launch_url', _LAUNCH_URL_MAX_LENGTH,
    )
    oidc_url = _http_url(
        section.get('oidc_url', configuration.lti_1p3_oidc_url), 'lti_1p3.oidc_url', _OIDC_URL_MAX_LENGTH,
    )
    redirect_uris = _http_url_list(
        section.get('redirect_uris', configuration.lti_1p3_redirect_uris), 'lti_1p3.redirect_uris',
    )
    mode = section.get('tool_key_mode', configuration.lti_1p3_tool_key_mode)
    if mode not in _TOOL_KEY_MODES:
        _invalid('lti_1p3.tool_key_mode', _('A supported LTI 1.3 tool-key mode is required.'))
    tool_public_key = section.get('tool_public_key', configuration.lti_1p3_tool_public_key)
    tool_keyset_url = section.get('tool_keyset_url', configuration.lti_1p3_tool_keyset_url)
    if mode == 'public_key':
        if 'tool_keyset_url' in section:
            _invalid('lti_1p3.tool_keyset_url', _('Not accepted in public-key mode.'))
        tool_public_key = _public_key(tool_public_key, 'lti_1p3.tool_public_key')
        tool_keyset_url = ''
    else:
        if 'tool_public_key' in section:
            _invalid('lti_1p3.tool_public_key', _('Not accepted in keyset URL mode.'))
        tool_keyset_url = _http_url(tool_keyset_url, 'lti_1p3.tool_keyset_url', _KEYSET_URL_MAX_LENGTH)
        tool_public_key = ''

    configuration.lti_1p3_launch_url = launch_url
    configuration.lti_1p3_oidc_url = oidc_url
    configuration.lti_1p3_redirect_uris = redirect_uris
    configuration.lti_1p3_tool_key_mode = mode
    if {'tool_key_mode', 'tool_public_key', 'tool_keyset_url'} & set(section):
        configuration.lti_1p3_tool_public_key = tool_public_key
        configuration.lti_1p3_tool_keyset_url = tool_keyset_url


def _initial_version(stored_version, requested_version):
    """Return the one-time LTI version assignment for an unversioned converted row."""
    if stored_version is not None:
        _invalid('version', _('The LTI version is already set and cannot be changed.'))
    if requested_version not in (LTI_1P1, LTI_1P3):
        _invalid('version', _('A supported LTI version is required.'))
    return requested_version


def _validated_changes(configuration, changes):
    """Validate changes against the stored row and assign them to it."""
    _reject_unknown(changes, _UPDATE_MEMBERS)
    if 'version' in changes:
        # A converted row may have no version at all; it gets exactly one assignment, and the
        # rest of this call then validates against the version just chosen.
        configuration.version = _initial_version(configuration.version, changes['version'])
    if 'name' in changes:
        configuration.name = _nonblank_string(changes['name'], 'name', _NAME_MAX_LENGTH)
    if 'description' in changes:
        configuration.description = _optional_string(changes['description'], 'description')

    is_lti_1p3 = configuration.version == LTI_1P3
    connection_name = LTI_1P3 if is_lti_1p3 else LTI_1P1
    other_name = LTI_1P1 if is_lti_1p3 else LTI_1P3
    if other_name in changes:
        _invalid(other_name, _('Connection settings must match the configuration version.'))
    section = changes.get(connection_name)
    if connection_name in changes and not isinstance(section, dict):
        _invalid(connection_name, _('Invalid connection settings.'))
    if section:
        # Connection state is validated only when the request changes it, so an incomplete
        # converted configuration stays remediable through metadata, context, services and defaults.
        _reject_unknown(section, _UPDATE_CONNECTION_MEMBERS[connection_name], prefix=f'{connection_name}.')
        if is_lti_1p3:
            _apply_lti_1p3_changes(configuration, section)
        else:
            _apply_lti_1p1_changes(configuration, section)

    services = _stored_services(configuration)
    if 'services' in changes:
        provided_services = changes['services']
        if not isinstance(provided_services, dict):
            _invalid('services', _('Invalid reusable configuration settings.'))
        _reject_unknown(provided_services, _SERVICE_MEMBERS, prefix='services.')
        services.update(provided_services)
    for field, value in service_configuration_values(_validated_services(services)).items():
        setattr(configuration, field, value)

    if 'defaults' in changes:
        for key, value in _validated_defaults(changes['defaults']).items():
            setattr(configuration, key, value)


def update_reusable_configuration(actor, config_id, changes):
    """Update one visible, manageable configuration inside one transaction.

    The actor is authorized through the Creation Context policy; changes is a
    parsed wire mapping without Creation Context or identity members. Returns
    the updated row and never returns credentials.
    """
    if not isinstance(changes, dict):
        _invalid(None, _('Invalid reusable configuration changes.'))

    policy = CreationContextPolicy(actor)
    try:
        with transaction.atomic():
            configuration = _locked_visible_configuration(policy, config_id)
            if not policy.can_manage(configuration):
                raise ReusableConfigurationError('forbidden', _('You cannot manage this reusable configuration.'))
            if set(changes) == {'context'} and configuration.context_type is None:
                # One immutable first assignment for a converted row. Context-only, so an
                # incomplete configuration can be assigned before its settings are filled.
                context = policy.authorize_assignment(changes['context'])
                configuration.context_type = context.type
                configuration.context_key = context.key
                configuration.save()
                return configuration
            _validated_changes(configuration, changes)
            configuration.save()
    except IntegrityError:
        _conflict(_('The update conflicts with an existing configuration.'))
    return configuration
