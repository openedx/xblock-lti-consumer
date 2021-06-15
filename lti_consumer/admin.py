"""
Admin views for LTI related models.
"""
from config_models.admin import KeyedConfigurationModelAdmin
from django.contrib import admin

from lti_consumer.forms import CourseEditLTIFieldsEnabledAdminForm
from lti_consumer.models import (
    CourseEditLTIFieldsEnabledFlag,
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


class CourseEditLTIFieldsEnabledFlagAdmin(KeyedConfigurationModelAdmin):
    """
    Admin for LTI Fields Editing feature on course-by-course basis.
    Allows searching by course id.
    """
    form = CourseEditLTIFieldsEnabledAdminForm
    search_fields = ['course_id']
    fieldsets = (
        (None, {
            'fields': ('course_id', 'enabled'),
            'description': 'Enter a valid course id. If it is invalid, an error message will be displayed.'
        }),
    )


admin.site.register(CourseEditLTIFieldsEnabledFlag, CourseEditLTIFieldsEnabledFlagAdmin)
admin.site.register(LtiConfiguration, LtiConfigurationAdmin)
admin.site.register(LtiAgsLineItem)
admin.site.register(LtiAgsScore)
admin.site.register(LtiDlContentItem)
