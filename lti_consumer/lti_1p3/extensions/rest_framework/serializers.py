"""
Serializers for LTI-related endpoints
"""
from django.utils import timezone
from rest_framework import serializers, ISO_8601
from rest_framework.reverse import reverse
from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import UsageKey

from lti_consumer.models import LtiAgsLineItem, LtiAgsScore
from lti_consumer.lti_1p3.constants import LTI_1P3_CONTEXT_ROLE_MAP


class UsageKeyField(serializers.Field):
    """
    Serializer field for a model UsageKey field.

    Recreated here since we cannot import directly from
    from the platform like so:
    `from openedx.core.lib.api.serializers import UsageKeyField`
    """
    def to_representation(self, value):
        """
        Convert a usage key to unicode.
        """
        return str(value)

    def to_internal_value(self, data):
        """
        Convert unicode to a usage key.
        """
        try:
            return UsageKey.from_string(data)
        except InvalidKeyError as err:
            raise serializers.ValidationError(f"Invalid usage key: {data!r}") from err


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

    # NOTE: `serializers.DateTimeField` always outputs the value in the local timezone of the server running the code
    # This is because Django is time aware (see settings.USE_TZ) and because Django is unable to determine the timezone
    # of the person making the API request, thus falling back on the local timezone. As such, since all outputs will
    # necessarily be in a singular timezone, that timezone should be `utc`
    timestamp = serializers.DateTimeField(input_formats=[ISO_8601], format=ISO_8601, default_timezone=timezone.utc)
    scoreGiven = serializers.FloatField(source='score_given', required=False, allow_null=True, default=None)
    scoreMaximum = serializers.FloatField(source='score_maximum', required=False, allow_null=True, default=None)
    comment = serializers.CharField(required=False, allow_null=True)
    activityProgress = serializers.CharField(source='activity_progress')
    gradingProgress = serializers.CharField(source='grading_progress')
    userId = serializers.CharField(source='user_id')

    def validate_timestamp(self, value):
        """
        Ensure that if an existing record is being updated, that the timestamp is in the after the existing one
        """
        if self.instance:
            if self.instance.timestamp > value:
                raise serializers.ValidationError('Score timestamp can only be updated to a later point in time')

            if self.instance.timestamp == value:
                raise serializers.ValidationError('Score already exists for the provided timestamp')

        return value

    def validate_scoreMaximum(self, value):
        """
        Ensure that scoreMaximum is set when scoreGiven is provided and not None
        """
        if not value and self.initial_data.get('scoreGiven', None) is not None:
            raise serializers.ValidationError('scoreMaximum is a required field when providing a scoreGiven value.')
        return value

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
        request = self.context.get('request')
        return reverse(
            'lti_consumer:lti-ags-view-results',
            kwargs={
                'lti_config_id': obj.line_item.lti_configuration.id,
                'pk': obj.line_item.pk,
                'user_id': obj.user_id,
            },
            request=request,
        )

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


# pylint: disable=abstract-method
class LtiDlTimeDeltaSerializer(serializers.Serializer):
    """
    LTI Deep Linking - Time Delta seralizer.

    Used in some LTI content types, it's a serializer
    containing `startDateTime` and `endDateTime` to signal
    if content if available or gra
    """
    startDateTime = serializers.DateTimeField(
        input_formats=[ISO_8601],
        format=ISO_8601,
        default_timezone=timezone.utc,
        required=False,
    )
    endDateTime = serializers.DateTimeField(
        input_formats=[ISO_8601],
        format=ISO_8601,
        default_timezone=timezone.utc,
        required=False,
    )


# pylint: disable=abstract-method
class LtiDlLineItemSerializer(serializers.Serializer):
    """
    LTI Deep linking AGS Serializer - Specific for LTI Resource Link.

    Used when a deep link is able to send back grades to the platform.
    """
    label = serializers.CharField(max_length=255, required=False)
    scoreMaximum = serializers.FloatField(required=False)
    resourceId = serializers.CharField(max_length=255, required=False)
    tag = serializers.CharField(max_length=255, required=False)


# pylint: disable=abstract-method
class LtiDlLtiResourceLinkSerializer(serializers.Serializer):
    """
    LTI Deep Linking - LTI Resource Link Serializer.

    This serializer implements validation for the LTI Resource Link content type.

    Reference:
    http://www.imsglobal.org/spec/lti-dl/v2p0#lti-resource-link
    """
    url = serializers.URLField(max_length=500, required=False)
    title = serializers.CharField(max_length=255, required=False)
    custom = serializers.DictField(required=False)
    lineItem = LtiDlLineItemSerializer(required=False)
    available = LtiDlTimeDeltaSerializer(required=False)
    submission = LtiDlTimeDeltaSerializer(required=False)


# pylint: disable=abstract-method
class LtiDLIconPropertySerializer(serializers.Serializer):
    """
    LTI Deep Linking - `icon` or `thumbnail` property serializer.
    """
    url = serializers.URLField(max_length=500)
    width = serializers.IntegerField(min_value=1)
    height = serializers.IntegerField(min_value=1)


# pylint: disable=abstract-method
class LtiDlEmbedPropertySerializer(serializers.Serializer):
    """
    LTI Deep Linking - `embed` property serializer.
    """
    html = serializers.CharField()


# pylint: disable=abstract-method
class LtiDlWindowPropertySerializer(serializers.Serializer):
    """
    LTI Deep Linking - `window` property serializer.
    """
    targetName = serializers.CharField(max_length=255, required=False)
    width = serializers.IntegerField(min_value=1, required=False)
    height = serializers.IntegerField(min_value=1, required=False)
    windowFeatures = serializers.CharField(required=False)


# pylint: disable=abstract-method
class LtiDlIframePropertySerializer(serializers.Serializer):
    """
    LTI Deep Linking - `iframe` property serializer.
    """
    src = serializers.URLField(max_length=500)
    width = serializers.IntegerField(min_value=1)
    height = serializers.IntegerField(min_value=1)


# pylint: disable=abstract-method
class LtiDlLinkSerializer(serializers.Serializer):
    """
    LTI Deep Linking - Link Serializer.

    This serializer implements validation for the Link content type.

    Reference:
    http://www.imsglobal.org/spec/lti-dl/v2p0#link
    """
    url = serializers.URLField(max_length=500)
    title = serializers.CharField(max_length=255, required=False)
    text = serializers.CharField(required=False)
    icon = LtiDLIconPropertySerializer(required=False)
    thumbnail = LtiDLIconPropertySerializer(required=False)
    embed = LtiDlEmbedPropertySerializer(required=False)
    window = LtiDlWindowPropertySerializer(required=False)
    iframe = LtiDlIframePropertySerializer(required=False)


# pylint: disable=abstract-method
class LtiDlHtmlSerializer(serializers.Serializer):
    """
    LTI Deep Linking - html Serializer.

    This serializer implements validation for the HTML Fragment content type.

    Reference:
    http://www.imsglobal.org/spec/lti-dl/v2p0#html-fragment
    """
    html = serializers.CharField()
    title = serializers.CharField(max_length=255, required=False)
    text = serializers.CharField(required=False)


# pylint: disable=abstract-method
class LtiDlImageSerializer(serializers.Serializer):
    """
    LTI Deep Linking - image Serializer.

    This serializer implements validation for the Image content type.

    Reference:
    http://www.imsglobal.org/spec/lti-dl/v2p0#image
    """
    url = serializers.URLField(max_length=500)
    title = serializers.CharField(max_length=255, required=False)
    text = serializers.CharField(required=False)
    icon = LtiDLIconPropertySerializer(required=False)
    thumbnail = LtiDLIconPropertySerializer(required=False)
    width = serializers.IntegerField(min_value=1, required=False)
    height = serializers.IntegerField(min_value=1, required=False)


class LtiContextSerializer(serializers.Serializer):
    """
    Serializer for a LTI Context
    """
    id = UsageKeyField()


class LtiNrpsContextMemberBasicSerializer(serializers.Serializer):
    """
    Non PII fields serializer for Context Member.
    """
    status = serializers.CharField(default='Active')
    user_id = serializers.CharField(source='external_id')
    roles = serializers.SerializerMethodField()

    def get_roles(self, user_info):
        """
        Prepare and return Context Roles for user.
        """
        roles = []
        for role in user_info['roles']:
            if LTI_1P3_CONTEXT_ROLE_MAP.get(role):
                roles += LTI_1P3_CONTEXT_ROLE_MAP[role]
        return set(roles)


class LtiNrpsContextMemberPIISerializer(LtiNrpsContextMemberBasicSerializer):
    """
    Personally identifiable information serializer for Context Member.
    """
    name = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)


# pylint: disable=abstract-method
class LtiNrpsContextMembershipBasicSerializer(serializers.Serializer):
    """
    Serializer for LTI NRPS Context Memberships Endpoint Response
    """
    id = serializers.CharField()
    context = LtiContextSerializer()
    members = LtiNrpsContextMemberBasicSerializer(many=True)


# pylint: disable=abstract-method
class LtiNrpsContextMembershipPIISerializer(LtiNrpsContextMembershipBasicSerializer):
    """
    Serializer for a LTI NRPS Context Memberships Endpoint Response with PII fields
    """
    members = LtiNrpsContextMemberPIISerializer(many=True)
