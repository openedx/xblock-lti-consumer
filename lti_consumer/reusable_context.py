"""Creation Context policy for reusable LTI configurations.

Owns Creation Context normalization, create-time validity, query-backed
visibility and manage authority. Open edX facts are reached only through the
adapter in plugin.compat; one policy instance serves one request or one
mutation call and caches only its own lookups.
"""

from dataclasses import dataclass

from ccx_keys.locator import CCXLocator
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import CourseKey
from opaque_keys.edx.locator import CourseLocator

from lti_consumer.exceptions import ReusableConfigurationError
from lti_consumer.models import ReusableLtiConfiguration
from lti_consumer.plugin import compat

CONTEXT_TYPES = ('course', 'organization', 'site')


@dataclass(frozen=True)
class CreationContext:
    """The single immutable context chosen when a configuration is created."""

    type: str
    key: str = ''


def _invalid(message, field):
    """Raise an invalid-category error addressed to one member."""
    raise ReusableConfigurationError('invalid', message, field=field)


def _forbidden(message):
    """Raise a forbidden-category error with no member address."""
    raise ReusableConfigurationError('forbidden', message)


class CreationContextPolicy:
    """Actor-scoped authority over Creation Contexts, with per-instance caches."""

    def __init__(self, actor):
        self._actor = actor
        self._course_admin_cache = {}
        self._accessible_course_keys_cache = None
        self._organization_keys_cache = None

    # Creation

    def authorize_creation(self, raw_context):
        """Return the canonical Creation Context for an authorized create.

        Order matters: shape, in-process normalization, authority, then the
        organization registry for authorized callers only.
        """
        context_type, raw_key = self._context_shape(raw_context)
        if context_type == 'site':
            self._require_superuser()
            return CreationContext(type='site')
        if context_type == 'organization':
            organization_key = self._normalize_organization_key(raw_key)
            self._require_superuser()
            self._resolve_organization(organization_key)
            return CreationContext(type='organization', key=organization_key)

        course_key = self._normalize_course_key(raw_key)
        if len(str(course_key)) > self._context_key_max_length():
            _invalid(_('The context key is too long.'), 'context.key')
        self._authorize_course_context(course_key)
        return CreationContext(type='course', key=str(course_key))

    # Reads

    def visible_configurations(self, course_key=None):
        """Return a lazy, actor-constrained queryset of configurations.

        A course_key restricts the result to configurations whose Creation
        Context covers that course; a malformed key is an addressed invalid
        error, while a valid key the actor cannot reach yields an empty result.
        """
        configurations = ReusableLtiConfiguration.objects.all()
        requested_course_key = None
        if course_key is not None:
            requested_course_key = self._normalize_course_key(course_key, field='course_key')

        if not self._is_authenticated():
            return configurations.none()
        if not self._actor.is_superuser:
            accessible_keys = self._accessible_course_keys()
            if not accessible_keys:
                return configurations.none()
            if requested_course_key is None:
                course_keys = accessible_keys
            elif requested_course_key in accessible_keys:
                course_keys = [requested_course_key]
            else:
                return configurations.none()
        elif requested_course_key is None:
            return configurations
        else:
            course_keys = [requested_course_key]

        return configurations.filter(
            Q(context_type='site') |
            Q(context_type='course', context_key__in=[str(key) for key in course_keys]) |
            Q(context_type='organization', context_key__in={key.org.lower() for key in course_keys})
        )

    def can_manage(self, configuration):
        """Return whether this actor may manage one configuration.

        Never raises and never consults the organization registry: a persisted
        organization context is taken as stored, including after inactivation.
        """
        if not self._is_authenticated():
            return False
        if configuration.context_type not in CONTEXT_TYPES:
            return False
        if configuration.context_type in ('organization', 'site'):
            return bool(self._actor.is_superuser)
        if not configuration.context_key:
            return False
        try:
            course_key = self._normalize_course_key(configuration.context_key)
        except ReusableConfigurationError:
            return False
        if isinstance(course_key, CCXLocator) and not self._actor.is_superuser:
            return False
        if self._actor.is_superuser:
            return True
        return self._user_is_course_admin(course_key)

    # Context shape, normalization and authority

    @staticmethod
    def _context_shape(raw_context):
        """Return (type, key) for a well-formed context, or raise invalid."""
        if not isinstance(raw_context, dict):
            _invalid(_('A context with a type of course, organization, or site is required.'), 'context')
        if set(raw_context) - {'type', 'key'}:
            _invalid(_('The context must contain only type and key.'), 'context')
        context_type = raw_context.get('type')
        if context_type not in CONTEXT_TYPES:
            _invalid(_('A context type of course, organization, or site is required.'), 'context.type')
        if context_type == 'site':
            if 'key' in raw_context:
                _invalid(_('The site context must not include a key.'), 'context.key')
            return context_type, None
        key = raw_context.get('key')
        if not isinstance(key, str) or not key.strip():
            _invalid(_('A context key is required for course and organization contexts.'), 'context.key')
        return context_type, key.strip()

    @staticmethod
    def _normalize_course_key(value, field='context.key'):
        """Return a canonical CourseLocator, or raise an addressed error."""
        try:
            course_key = value if isinstance(value, CourseKey) else CourseKey.from_string(value)
        except (InvalidKeyError, TypeError, ValueError):
            _invalid(_('Invalid course key.'), field)
        if not isinstance(course_key, CourseLocator):
            _invalid(_('A course key is required.'), field)
        if not all((course_key.org, course_key.course, course_key.run)):
            _invalid(_('A full course key is required.'), field)
        return course_key.for_branch(None).version_agnostic()

    @staticmethod
    def _normalize_organization_key(raw_key):
        """Return the trimmed, lowercased organization short name."""
        organization_key = raw_key.lower()
        if len(organization_key) > CreationContextPolicy._context_key_max_length():
            _invalid(_('The context key is too long.'), 'context.key')
        return organization_key

    @staticmethod
    def _context_key_max_length():
        """Return the stored maximum length for a Creation Context key."""
        return ReusableLtiConfiguration._meta.get_field('context_key').max_length

    def _require_authenticated(self):
        """Raise forbidden unless the actor is authenticated."""
        if not self._is_authenticated():
            _forbidden(_('Authentication is required to manage reusable configurations.'))

    def _require_superuser(self):
        """Raise forbidden unless the actor is a platform administrator."""
        self._require_authenticated()
        if not self._actor.is_superuser:
            _forbidden(_('Only a platform administrator may use this Creation Context.'))

    def _authorize_course_context(self, course_key):
        """Raise forbidden unless the actor may manage this course context."""
        self._require_authenticated()
        if self._actor.is_superuser:
            return
        # CCX courses are outside Studio's catalog, so deny them before any role lookup.
        if isinstance(course_key, CCXLocator):
            _forbidden(_('Only a platform administrator may use a CCX course context.'))
        if not self._user_is_course_admin(course_key):
            _forbidden(_('Only a course administrator may use this course context.'))

    def _resolve_organization(self, organization_key):
        """Raise invalid unless the key names one unambiguous active organization."""
        if organization_key not in self._active_organization_keys():
            _invalid(_('Organization must match one unambiguous active registered organization.'), 'context.key')

    def _active_organization_keys(self):
        """Return lowercased keys for unique, active organization short names."""
        if self._organization_keys_cache is None:
            registered = {}
            for organization in compat.get_active_organizations():
                short_name = organization.get('short_name')
                if isinstance(short_name, str):
                    registered.setdefault(short_name.lower(), set()).add(short_name)
            self._organization_keys_cache = {key for key, names in registered.items() if len(names) == 1}
        return self._organization_keys_cache

    # Platform facts

    def _is_authenticated(self):
        """Return whether the actor is authenticated, without any platform read."""
        return bool(getattr(self._actor, 'is_authenticated', False))

    def _accessible_course_keys(self):
        """Return normalized Studio-accessible course keys, skipping malformed ones."""
        if self._accessible_course_keys_cache is None:
            keys = []
            for key in compat.get_studio_accessible_course_keys(self._actor):
                try:
                    keys.append(self._normalize_course_key(key))
                except ReusableConfigurationError:
                    continue
            self._accessible_course_keys_cache = keys
        return self._accessible_course_keys_cache

    def _user_is_course_admin(self, course_key):
        """Return the cached platform course-admin role check for one course."""
        if course_key not in self._course_admin_cache:
            self._course_admin_cache[course_key] = compat.user_is_course_admin(self._actor, course_key)
        return self._course_admin_cache[course_key]
