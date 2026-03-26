"""
Admin views for LTI related models.
"""
from config_models.admin import KeyedConfigurationModelAdmin
from django.contrib import admin

from lti_consumer.forms import CourseAllowPIISharingInLTIAdminForm
from lti_consumer.models import (
    CourseAllowPIISharingInLTIFlag,
    Lti1p3Passport,
    LtiAgsLineItem,
    LtiAgsScore,
    LtiConfiguration,
    LtiDlContentItem,
)


class LtiConfigurationInline(admin.TabularInline):
    """
    Inline for the LtiConfiguration models in Lti1p3Passport.
    """
    model = LtiConfiguration
    extra = 0
    can_delete = False
    fields = ('location',)

    def has_change_permission(self, request, obj=None):  # pragma: nocover
        return False

    def has_delete_permission(self, request, obj=None):  # pragma: nocover
        return False

    def has_add_permission(self, request, obj=None):  # pragma: nocover
        return False


@admin.register(LtiConfiguration)
class LtiConfigurationAdmin(admin.ModelAdmin):
    """
    Admin view for LtiConfiguration models.

    Makes the location field read-only to avoid issues.
    """
    readonly_fields = ('location', 'config_id')


@admin.register(Lti1p3Passport)
class Lti1p3PassportAdmin(admin.ModelAdmin):
    """
    Admin view for Lti1p3Passport models.
    """
    list_display = ('passport_id', 'lti_1p3_client_id')
    inlines = [LtiConfigurationInline]


@admin.register(CourseAllowPIISharingInLTIFlag)
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


admin.site.register(LtiAgsLineItem)
admin.site.register(LtiAgsScore)
admin.site.register(LtiDlContentItem)
