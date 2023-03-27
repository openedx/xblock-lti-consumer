"""
Template tags and helper functions for sanitizing html.
"""
import bleach

from django import template
from django.utils.safestring import mark_safe
register = template.Library()


@register.filter()
def lti_sanitize(html):
    """
    Sanitize a html fragment with bleach.
    """
    allowed_tags = bleach.sanitizer.ALLOWED_TAGS | {'img'}
    allowed_attributes = dict(bleach.sanitizer.ALLOWED_ATTRIBUTES, **{'img': ['src', 'alt']})
    sanitized_html = bleach.clean(html, tags=allowed_tags, attributes=allowed_attributes)
    return mark_safe(sanitized_html)
