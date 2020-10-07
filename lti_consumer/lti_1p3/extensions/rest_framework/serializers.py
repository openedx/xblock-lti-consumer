"""
Serializers for LTI-related endpoints
"""
from rest_framework import serializers
from rest_framework.reverse import reverse
from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import UsageKey

from lti_consumer.models import LtiAgsLineItem, LtiAgsScore


class UsageKeyField(serializers.Field):
    """
    Serializer field for a model UsageKey field.

    Recreated here since we cannot import directly from
    from the platform like so:
    `from openedx.core.lib.api.serializers import UsageKeyField`
    """
    # pylint: disable=arguments-differ
    def to_representation(self, data):
        """
        Convert a usage key to unicode.
        """
        return str(data)

    def to_internal_value(self, data):
        """
        Convert unicode to a usage key.
        """
        try:
            return UsageKey.from_string(data)
        except InvalidKeyError:
            raise serializers.ValidationError("Invalid usage key: {}".format(data))


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
        "resourceLinkId" : "1g3k4dlk49fk",
        "startDateTime": "2018-03-06T20:05:02Z",
        "endDateTime": "2018-04-06T22:05:03Z",
    }

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


class LtiAgsScoreSerializer(serializers.ModelSerializer):
    """
    LTI AGS LineItemScore Serializer.

    This maps out the internally stored LtiAgsScore to
    the LTI-AGS API Specification, as shown in the example
    response below:

    {
      "timestamp": "2017-04-16T18:54:36.736+00:00",
      "scoreGiven" : 83,
      "scoreMaximum" : 100,
      "comment" : "This is exceptional work.",
      "activityProgress" : "Completed",
      "gradingProgress": "FullyGraded",
      "userId" : "5323497"
    }

    Reference:
    https://www.imsglobal.org/spec/lti-ags/v2p0#example-application-vnd-ims-lis-v1-score-json-representation
    """

    timestamp = serializers.DateTimeField()
    # All 'scoreGiven' values MUST be positive numeric (including 0).
    # 'scoreMaximum' represents the denominator and MUST be present when 'scoreGiven' is present
    scoreGiven = serializers.FloatField(source='score_given', required=False, allow_null=True, default=None)
    scoreMaximum = serializers.FloatField(source='score_maximum', required=False, allow_null=True, default=None)
    comment = serializers.CharField(required=False, allow_null=True)
    activityProgress = serializers.CharField(source='activity_progress')
    gradingProgress = serializers.CharField(source='grading_progress')
    userId = serializers.CharField(source='user_id')

    def validate_scoreGiven(self, value):
        if not self.instance and value is None:
            raise serializers.ValidationError('Cannot delete score. No score currently exists for this user')
        return value

    def validate_scoreMaximum(self, value):
        if self.initial_data.get('scoreGiven', None) and value is None:
            raise serializers.ValidationError('Cannot have empty scoreMaximum when scoreGiven is set')
        return value

    def validate_timestamp(self, value):
        if self.instance:
            if self.instance.timestamp > value:
                raise serializers.ValidationError('Score timestamp can only be updated to a later point in time')
            elif self.instance.timestamp == value:
                raise serializers.ValidationError('Score already exists for the provided timestamp')
        return value

    def update(self, instance, validated_data):
        # When 'scoreGiven' is not present, this indicates there is presently no score for that user,
        # and the platform should clear any previous score value it may have previously received from
        # the tool and stored for that user and line item
        if instance and validated_data.get('score_given', None) is None:
            instance.delete()
            return instance

        return super().update(instance, validated_data)

    class Meta:
        model = LtiAgsScore
        fields = (
            'timestamp',
            'scoreGiven',
            'scoreMaximum',
            'comment',
            'activityProgress',
            'gradingProgress',
            'userId',
        )


class LtiAgsResultSerializer(serializers.ModelSerializer):
    """
    LTI AGS LineItemResult Serializer.

    This maps out the internally stored LtiAgsScpre to
    the LTI-AGS API Specification, as shown in the example
    response below:

    {
      "id": "https://lms.example.com/context/2923/lineitems/1/results/5323497",
      "scoreOf": "https://lms.example.com/context/2923/lineitems/1",
      "userId": "5323497",
      "resultScore": 0.83,
      "resultMaximum": 1,
      "comment": "This is exceptional work."
    }

    Reference:
    https://www.imsglobal.org/spec/lti-ags/v2p0#example-application-vnd-ims-lis-v1-score-json-representation
    """

    id = serializers.SerializerMethodField()
    scoreOf = serializers.SerializerMethodField()
    userId = serializers.CharField(source='user_id')
    resultScore = serializers.FloatField(source='score_given')
    resultMaximum = serializers.SerializerMethodField()
    comment = serializers.CharField()

    def get_id(self, obj):
        scoreOf = self.get_scoreOf(obj)
        return '/'.join([scoreOf, 'results', obj.user_id])

    def get_scoreOf(self, obj):
        request = self.context.get('request')
        return reverse(
            'lti_consumer:lti-ags-view-detail',
            kwargs={
                'lti_config_id': obj.line_item.lti_configuration.id,
                'pk': obj.line_item.pk
            },
            request=request,
        )

    def get_resultMaximum(self, obj):
        if obj.score_maximum <= 0:
            return 1

        return obj.score_maximum

    class Meta:
        model = LtiAgsScore
        fields = (
            'id',
            'scoreOf',
            'userId',
            'resultScore',
            'resultMaximum',
            'comment',
        )
