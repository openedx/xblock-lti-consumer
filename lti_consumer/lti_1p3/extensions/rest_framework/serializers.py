"""
Serializers for LTI-related endpoints
"""
import six

from rest_framework import serializers
from rest_framework.reverse import reverse
from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import UsageKey

from lti_consumer.models import LtiAgsLineItem


class UsageKeyField(serializers.Field):
    """
    Serializer field for a model UsageKey field.

    Recreated here since we cannot import directly from
    from the platform like so:
    `from openedx.core.lib.api.serializers import UsageKeyField`
    """
    # pylint: disable=arguments-differ
    def to_representation(self, data):
        """Convert a usage key to unicode. """
        return six.text_type(data)

    def to_internal_value(self, data):
        """Convert unicode to a usage key. """
        try:
            return UsageKey.from_string(data)
        except InvalidKeyError:
            raise serializers.ValidationError(u"Invalid usage key: {}".format(data))


class LtiAgsLineItemSerializer(serializers.ModelSerializer):
    """
    LTI AGS LineItem Serializer.

    This maps out the internally stored LineItemParameters to
    the LTI-AGS API Specification, as shown in the example
    response below:

    {
        "id" : "https://lms.example.com/context/2923/lineitems/1",
        "scoreMaximum" : 60,
        "label" : "Chapter 5 Test",
        "resourceId" : "a-9334df-33",
        "tag" : "grade",
        "resourceLinkId" : "1g3k4dlk49fk"
        "startDateTime": "2018-03-06T20:05:02Z"
        "endDateTime": "2018-04-06T22:05:03Z"
    }

    Note: The platform MUST NOT modify the 'resourceId', 'resourceLinkId' and 'tag' values.

    Reference:
    https://www.imsglobal.org/spec/lti-ags/v2p0#example-application-vnd-ims-lis-v2-lineitem-json-representation
    """
    # Id needs to be overriden and be a URL to the LineItem endpoint
    id = serializers.SerializerMethodField()

    # Mapping from snake_case to camelCase
    resourceId = serializers.CharField(source='resource_id')
    scoreMaximum = serializers.IntegerField(source='score_maximum')
    resourceLinkId = UsageKeyField(required=False, source='resource_link_id')
    startDateTime = serializers.DateTimeField(required=False, source='start_date_time')
    endDateTime = serializers.DateTimeField(required=False, source='end_date_time')

    def get_id(self, obj):
        request = self.context.get('request')
        return reverse(
            'lti_consumer:lti-ags-view-detail',
            kwargs={
                'lti_config_id': obj.lti_configuration.id,
                'pk': obj.pk
            },
            request=request,
        )

    class Meta:
        model = LtiAgsLineItem
        fields = (
            'id',
            'resourceId',
            'scoreMaximum',
            'label',
            'tag',
            'resourceLinkId',
            'startDateTime',
            'endDateTime',
        )
