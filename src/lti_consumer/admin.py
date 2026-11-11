"""
Admin views for LTI related models.
"""
from config_models.admin import KeyedConfigurationModelAdmin
from django.contrib import admin
from django.contrib.admin.utils import flatten_fieldsets
from django.urls import reverse
from django.utils.html import format_html
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
from lti_consumer.plugin import compat


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


@admin.register(ReusableLtiConfiguration)
class ReusableLtiConfigurationAdmin(admin.ModelAdmin):
    """
    Inspection-only admin for reusable LTI configurations.

    Global Staff-only access; add/change/delete are denied for every role,
    superusers included. The fieldsets are the explicit detail allowlist,
    rendered read-only; the platform signing private key value is not listed.
    """
    list_display = ('name', 'version', 'passport_id', 'context_type', 'updated_at')
    list_filter = ('version', 'context_type')
    search_fields = ('name', 'passport_id')
    actions = None

    fieldsets = (
        (_('Identity'), {
            'fields': ('name', 'passport_id', 'version', 'description', 'is_active', 'created_at', 'updated_at'),
        }),
        # Translators: "Creation Context" is the course, organization or site the configuration was created in.
        (_('Creation Context'), {
            'fields': ('context_type', 'context_key'),
        }),
        (_('LTI 1.1'), {
            'fields': ('lti_1p1_launch_url', 'lti_1p1_client_key', 'lti_1p1_client_secret'),
        }),
        (_('LTI 1.3'), {
            'fields': (
                'lti_1p3_launch_url',
                'lti_1p3_oidc_url',
                'lti_1p3_redirect_uris',
                'lti_1p3_client_id',
                'lti_1p3_deployment_id',
                'lti_1p3_tool_key_mode',
                'lti_1p3_tool_public_key',
                'lti_1p3_tool_keyset_url',
                'lti_1p3_internal_private_key_id',
                'lti_1p3_internal_public_jwk',
            ),
        }),
        # Translators: "Services" means the LTI Advantage services (deep linking, AGS, NRPS).
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
        (_('Privacy'), {
            'fields': (
                'pii_share_username',
                'pii_share_full_name',
                'pii_share_email',
                'data_sharing_notice',
                'require_user_confirmation',
                'hide_external_tool',
            ),
        }),
    )
    readonly_fields = flatten_fieldsets(fieldsets)

    def get_fieldsets(self, request, obj=None):
        # A count replaces the inline: rendering every bound placement row is unbounded.
        # The link needs view access the placement admin already grants, or it is refused.
        placement_admin = self.admin_site.get_model_admin(LtiConfiguration)
        field = 'placements_link' if placement_admin.has_view_permission(request) else 'placements'
        return (*self.fieldsets, (_('Placements'), {'fields': (field,)}))

    @admin.display(description=_('Placements'))
    def placements(self, obj):
        """
        Read-only count of the placements bound to the configuration.
        """
        return obj.lticonfiguration_set.count()

    @admin.display(description=_('Placements'))
    def placements_link(self, obj):
        """
        The placement count, linked to the existing placement admin when allowed.
        """
        changelist = reverse('admin:lti_consumer_lticonfiguration_changelist')
        url = f'{changelist}?reusable_configuration__id__exact={obj.pk}'
        return format_html('<a href="{}">{}</a>', url, self.placements(obj))

    def has_module_permission(self, request):
        return compat.user_is_global_staff(request.user)

    def has_view_permission(self, request, obj=None):
        return compat.user_is_global_staff(request.user)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
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
    Read-only admin view for the retained Lti1p3Passport models.

    Runtime identity and keys come from reusable configurations, so this table is
    inspection-only: add, change and delete are denied for every role, superusers
    included. The table, its schema and its placement FK remain in place.
    """
    list_display = (
        'name',
        'context_key',
        'passport_id',
        'lti_1p3_client_id',
    )
    inlines = [LtiConfigurationInline]
    actions = None

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
