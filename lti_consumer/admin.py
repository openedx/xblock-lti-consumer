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
    ReusableLtiConfiguration,
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
    list_display = (
        'name',
        'context_key',
        'passport_id',
        'lti_1p3_client_id',
    )
    inlines = [LtiConfigurationInline]

    def get_queryset(self, request):
        return super().get_queryset(request).filter(reusable_configuration__isnull=True)

    @staticmethod
    def _is_reusable_passport(obj):
        return obj is not None and ReusableLtiConfiguration.objects.filter(lti_1p3_passport_id=obj.pk).exists()

    def has_view_permission(self, request, obj=None):
        return not self._is_reusable_passport(obj) and super().has_view_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        return not self._is_reusable_passport(obj) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return not self._is_reusable_passport(obj) and super().has_delete_permission(request, obj)


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
