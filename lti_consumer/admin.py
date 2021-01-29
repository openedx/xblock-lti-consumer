"""
Admin views for LTI related models.
"""
from django.contrib import admin
from lti_consumer.models import (
    LtiAgsLineItem,
    LtiConfiguration,
    LtiAgsScore,
    LtiDlContentItem,
)


class LtiConfigurationAdmin(admin.ModelAdmin):
    """
    Admin view for LtiConfiguration models.

    Makes the location field read-only to avoid issues.
    """
    readonly_fields = ('location', 'config_id')


admin.site.register(LtiConfiguration, LtiConfigurationAdmin)
admin.site.register(LtiAgsLineItem)
admin.site.register(LtiAgsScore)
admin.site.register(LtiDlContentItem)
