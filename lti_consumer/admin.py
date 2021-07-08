"""
Admin views for LTI related models.
"""
from config_models.admin import KeyedConfigurationModelAdmin
from django.contrib import admin

from lti_consumer.forms import CourseAllowPIISharingInLTIAdminForm
from lti_consumer.models import (
    CourseAllowPIISharingInLTIFlag,
    LtiAgsLineItem,
    LtiAgsScore,
    LtiConfiguration,
    LtiDlContentItem,
)


class LtiConfigurationAdmin(admin.ModelAdmin):
    """
    Admin view for LtiConfiguration models.

    Makes the location field read-only to avoid issues.
    """
    readonly_fields = ('location', 'config_id')


class CourseAllowPIISharingInLTIFlagAdmin(KeyedConfigurationModelAdmin):
    """
    Admin for enabling PII Sharing in LTI on course-by-course basis.
    Allows searching by course id.
    """
    form = CourseAllowPIISharingInLTIAdminForm
    search_fields = ['course_id']
    fieldsets = (
        (None, {
            'fields': ('course_id', 'enabled'),
            'description': 'Enter a valid course id. If it is invalid, an error message will be displayed.'
        }),
    )


admin.site.register(CourseAllowPIISharingInLTIFlag, CourseAllowPIISharingInLTIFlagAdmin)
admin.site.register(LtiConfiguration, LtiConfigurationAdmin)
admin.site.register(LtiAgsLineItem)
admin.site.register(LtiAgsScore)
admin.site.register(LtiDlContentItem)
