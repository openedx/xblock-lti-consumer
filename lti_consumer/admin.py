"""
Admin views for LTI related models.
"""
from config_models.admin import KeyedConfigurationModelAdmin
from django.contrib import admin
from django.contrib.admin.utils import flatten_fieldsets
from django.utils.translation import gettext_lazy as _

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
        # hide passports related to reusable configurations
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


@admin.register(ReusableLtiConfiguration)
class ReusableLtiConfigurationAdmin(admin.ModelAdmin):
    """
    Inspection-only admin for reusable LTI configurations.

    Superuser-only access; add/change/delete are always denied. The visible
    fields are an explicit allowlist that never exposes credentials, key
    material, normalized_name or the passport relation.
    """
    list_display = ('name', 'version', 'config_id', 'context_type', 'updated_at')
    list_filter = ('version', 'context_type')
    search_fields = ('name', 'config_id')
    actions = None

    # Explicit safe allowlist; readonly_fields is derived to stay in sync with it.
    fieldsets = (
        (_('Identity'), {
            'fields': ('name', 'description', 'config_id', 'version', 'created_at', 'updated_at'),
        }),
        # Translators: "Context" means the courses, organizations or the whole site it applies to, not OAuth scopes.
        (_('Context'), {
            'fields': ('context_type', 'context_key'),
        }),
        (_('LTI 1.1 connection'), {
            'fields': ('lti_1p1_launch_url',),
        }),
        (_('LTI 1.3 connection and registration'), {
            'fields': (
                'lti_1p3_launch_url',
                'lti_1p3_oidc_url',
                'lti_1p3_redirect_uris',
                'lti_1p3_client_id',
                'lti_1p3_deployment_id',
                'lti_1p3_tool_key_mode',
            ),
        }),
        # Translators: "Services" means the LTI Advantage services (deep linking, AGS, NRPS) enabled here.
        (_('Services'), {
            'fields': (
                'lti_advantage_deep_linking_enabled',
                'lti_advantage_deep_linking_launch_url',
                'lti_advantage_ags_mode',
                'lti_advantage_enable_nrps',
            ),
        }),
        (_('Placement defaults'), {
            'fields': (
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
            ),
        }),
    )
    readonly_fields = flatten_fieldsets(fieldsets)

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


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
