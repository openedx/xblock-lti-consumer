"""
Tests for LTI Advantage Assignments and Grades Service views.
"""
import json
from mock import patch, PropertyMock

from Cryptodome.PublicKey import RSA
import ddt
from django.urls import reverse
from jwkest.jwk import RSAKey
from rest_framework.test import APITransactionTestCase


from lti_consumer.lti_xblock import LtiConsumerXBlock
from lti_consumer.models import LtiConfiguration, LtiAgsLineItem, LtiAgsScore
from lti_consumer.tests.unit.test_utils import make_xblock


class LtiAgsLineItemViewSetTestCase(APITransactionTestCase):
    """
    Test `LtiAgsLineItemViewset` Class.
    """
    def setUp(self):
        super(LtiAgsLineItemViewSetTestCase, self).setUp()

        # Create custom LTI Block
        self.rsa_key_id = "1"
        rsa_key = RSA.generate(2048)
        self.key = RSAKey(
            key=rsa_key,
            kid=self.rsa_key_id
        )
        self.public_key = rsa_key.publickey().export_key()

        self.xblock_attributes = {
            'lti_version': 'lti_1p3',
            'lti_1p3_launch_url': 'http://tool.example/launch',
            'lti_1p3_oidc_url': 'http://tool.example/oidc',
            # We need to set the values below because they are not automatically
            # generated until the user selects `lti_version == 'lti_1p3'` on the
            # Studio configuration view.
            'lti_1p3_client_id': self.rsa_key_id,
            'lti_1p3_block_key': rsa_key.export_key('PEM'),
            # Intentionally using the same key for tool key to
            # allow using signing methods and make testing easier.
            'lti_1p3_tool_public_key': self.public_key,
        }
        self.xblock = make_xblock('lti_consumer', LtiConsumerXBlock, self.xblock_attributes)

        # Set dummy location so that UsageKey lookup is valid
        self.xblock.location = 'block-v1:course+test+2020+type@problem+block@test'

        # Create configuration
        self.lti_config = LtiConfiguration.objects.create(
            location=str(self.xblock.location),
            version=LtiConfiguration.LTI_1P3
        )
        # Preload XBlock to avoid calls to modulestore
        self.lti_config.block = self.xblock

        # Patch internal method to avoid calls to modulestore
        patcher = patch(
            'lti_consumer.models.LtiConfiguration.block',
            new_callable=PropertyMock,
            return_value=self.xblock
        )
        self.addCleanup(patcher.stop)
        self._lti_block_patch = patcher.start()

    def _set_lti_token(self, scopes=None):
        """
        Generates and sets a LTI Auth token in the request client.
        """
        if not scopes:
            scopes = ''

        consumer = self.lti_config.get_lti_consumer()
        token = consumer.key_handler.encode_and_sign({
            "iss": "https://example.com",
            "scopes": scopes,
        })
        # pylint: disable=no-member
        self.client.credentials(
            HTTP_AUTHORIZATION="Bearer {}".format(token)
        )


@ddt.ddt
class LtiAgsViewSetTokenTests(LtiAgsLineItemViewSetTestCase):
    """
    Test `LtiAgsLineItemViewset` token based requests/responses.
    """

    def setUp(self):
        super().setUp()

        # LineItem endpoint
        self.lineitem_endpoint = reverse(
            'lti_consumer:lti-ags-view-list',
            kwargs={
                "lti_config_id": self.lti_config.id
            }
        )

    def test_lti_ags_view_no_token(self):
        """
        Test the LTI AGS list view when there's no token.
        """
        response = self.client.get(self.lineitem_endpoint)
        self.assertEqual(response.status_code, 403)

    @ddt.data("Bearer invalid-token", "test", "Token with more items")
    def test_lti_ags_view_invalid_token(self, authorization):
        """
        Test the LTI AGS list view when there's an invalid token.
        """
        self.client.credentials(HTTP_AUTHORIZATION=authorization)  # pylint: disable=no-member
        response = self.client.get(self.lineitem_endpoint)

        self.assertEqual(response.status_code, 403)

    def test_lti_ags_token_missing_scopes(self):
        """
        Test the LTI AGS list view when there's a valid token without valid scopes.
        """
        self._set_lti_token()
        response = self.client.get(self.lineitem_endpoint)
        self.assertEqual(response.status_code, 403)


@ddt.ddt
class LtiAgsViewSetLineItemTests(LtiAgsLineItemViewSetTestCase):
    """
    Test `LtiAgsLineItemViewset` LineItem based requests/responses.
    """

    def setUp(self):
        super().setUp()

        # LineItem endpoint
        self.lineitem_endpoint = reverse(
            'lti_consumer:lti-ags-view-list',
            kwargs={
                "lti_config_id": self.lti_config.id
            }
        )

    @ddt.data(
        'https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly',
        'https://purl.imsglobal.org/spec/lti-ags/scope/lineitem'
    )
    def test_lti_ags_list_permissions(self, scopes):
        """
        Test the LTI AGS list view when there's token valid scopes.
        """
        self._set_lti_token(scopes)
        # Test with no LineItems
        response = self.client.get(self.lineitem_endpoint)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_lti_ags_list(self):
        """
        Test the LTI AGS list.
        """
        self._set_lti_token('https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly')

        # Create LineItem
        line_item = LtiAgsLineItem.objects.create(
            lti_configuration=self.lti_config,
            resource_id="test",
            resource_link_id=self.xblock.location,
            label="test label",
            score_maximum=100
        )

        # Retrieve & check
        response = self.client.get(self.lineitem_endpoint)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['content-type'], 'application/vnd.ims.lis.v2.lineitemcontainer+json')
        self.assertEqual(
            response.data,
            [
                {
                    'id': 'http://testserver/lti_consumer/v1/lti/{}/lti-ags/{}'.format(
                        self.lti_config.id,
                        line_item.id
                    ),
                    'resourceId': 'test',
                    'scoreMaximum': 100,
                    'label': 'test label',
                    'tag': '',
                    'resourceLinkId': self.xblock.location,
                    'startDateTime': None,
                    'endDateTime': None,
                }
            ]
        )

    def test_lti_ags_retrieve(self):
        """
        Test the LTI AGS retrieve endpoint.
        """
        self._set_lti_token('https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly')

        # Create LineItem
        line_item = LtiAgsLineItem.objects.create(
            lti_configuration=self.lti_config,
            resource_id="test",
            resource_link_id=self.xblock.location,
            label="test label",
            score_maximum=100
        )

        # Retrieve & check
        lineitem_detail_url = reverse(
            'lti_consumer:lti-ags-view-detail',
            kwargs={
                "lti_config_id": self.lti_config.id,
                "pk": line_item.id
            }
        )
        response = self.client.get(lineitem_detail_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            {
                'id': 'http://testserver/lti_consumer/v1/lti/{}/lti-ags/{}'.format(
                    self.lti_config.id,
                    line_item.id
                ),
                'resourceId': 'test',
                'scoreMaximum': 100,
                'label': 'test label',
                'tag': '',
                'resourceLinkId': self.xblock.location,
                'startDateTime': None,
                'endDateTime': None,
            }
        )

    def test_create_lineitem(self):
        """
        Test the LTI AGS LineItem Creation.
        """
        self._set_lti_token('https://purl.imsglobal.org/spec/lti-ags/scope/lineitem')

        # Create LineItem
        response = self.client.post(
            self.lineitem_endpoint,
            data=json.dumps({
                'resourceId': 'test',
                'scoreMaximum': 100,
                'label': 'test',
                'tag': 'score',
                'resourceLinkId': self.xblock.location,
            }),
            content_type="application/vnd.ims.lis.v2.lineitem+json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.data,
            {
                'id': 'http://testserver/lti_consumer/v1/lti/1/lti-ags/1',
                'resourceId': 'test',
                'scoreMaximum': 100,
                'label': 'test',
                'tag': 'score',
                'resourceLinkId': self.xblock.location,
                'startDateTime': None,
                'endDateTime': None,
            }
        )
        self.assertEqual(LtiAgsLineItem.objects.all().count(), 1)
        line_item = LtiAgsLineItem.objects.get()
        self.assertEqual(line_item.resource_id, 'test')
        self.assertEqual(line_item.score_maximum, 100)
        self.assertEqual(line_item.label, 'test')
        self.assertEqual(line_item.tag, 'score')
        self.assertEqual(str(line_item.resource_link_id), self.xblock.location)

    def test_create_lineitem_invalid_resource_link_id(self):
        """
        Test the LTI AGS Lineitem creation when passing invalid resource link id.
        """
        self._set_lti_token('https://purl.imsglobal.org/spec/lti-ags/scope/lineitem')

        # Create LineItem
        response = self.client.post(
            self.lineitem_endpoint,
            data=json.dumps({
                'resourceId': 'test',
                'scoreMaximum': 100,
                'label': 'test',
                'tag': 'score',
                'resourceLinkId': 'invalid-resource-link',
            }),
            content_type="application/vnd.ims.lis.v2.lineitem+json",
        )

        self.assertEqual(response.status_code, 400)


class LtiAgsViewSetScoresTests(LtiAgsLineItemViewSetTestCase):
    """
    Test `LtiAgsLineItemViewset` Score Publishing requests/responses.
    """

    def setUp(self):
        super().setUp()

        # Create LineItem
        self.line_item = LtiAgsLineItem.objects.create(
            lti_configuration=self.lti_config,
            resource_id="test",
            resource_link_id=self.xblock.location,
            label="test label",
            score_maximum=100
        )

        self.primary_user_id = "primary"
        self.secondary_user_id = "secondary"

        self.early_timestamp = "2020-01-01T18:54:36.736000+00:00"
        self.middle_timestamp = "2021-01-01T18:54:36.736000+00:00"
        self.late_timestamp = "2022-01-01T18:54:36.736000+00:00"

        # Scores endpoint
        self.scores_endpoint = reverse(
            'lti_consumer:lti-ags-view-scores',
            kwargs={
                "lti_config_id": self.lti_config.id,
                "pk": self.line_item.id
            }
        )

    def test_create_score(self):
        """
        Test the LTI AGS LineItem Score Creation.
        """
        self._set_lti_token('https://purl.imsglobal.org/spec/lti-ags/scope/score')

        # Create Score
        response = self.client.post(
            self.scores_endpoint,
            data=json.dumps({
                "timestamp": self.early_timestamp,
                "scoreGiven": 83,
                "scoreMaximum": 100,
                "comment": "This is exceptional work.",
                "activityProgress": LtiAgsScore.COMPLETED,
                "gradingProgress": LtiAgsScore.FULLY_GRADED,
                "userId": self.primary_user_id
            }),
            content_type="application/vnd.ims.lis.v1.score+json",
        )

        self.assertEqual(LtiAgsScore.objects.all().count(), 1)
        self.assertEqual(response.status_code, 201)

        # The serializer replaces `+00:00` with `Z`
        response_timestamp = self.early_timestamp.replace('+00:00', 'Z')
        self.assertEqual(
            response.data,
            {
                "timestamp": response_timestamp,
                "scoreGiven": 83.0,
                "scoreMaximum": 100.0,
                "comment": "This is exceptional work.",
                "activityProgress": LtiAgsScore.COMPLETED,
                "gradingProgress": LtiAgsScore.FULLY_GRADED,
                "userId": self.primary_user_id
            }
        )

        score = LtiAgsScore.objects.get(line_item=self.line_item, user_id=self.primary_user_id)
        self.assertEqual(score.line_item.id, self.line_item.id)
        self.assertEqual(score.timestamp.isoformat(), self.early_timestamp)
        self.assertEqual(score.score_given, 83.0)
        self.assertEqual(score.score_maximum, 100.0)
        self.assertEqual(score.activity_progress, LtiAgsScore.COMPLETED)
        self.assertEqual(score.grading_progress, LtiAgsScore.FULLY_GRADED)
        self.assertEqual(score.user_id, self.primary_user_id)

    def test_create_multiple_scores_with_multiple_users(self):
        """
        Test the LTI AGS LineItem Score Creation on the same LineItem for different users.
        """
        self._set_lti_token('https://purl.imsglobal.org/spec/lti-ags/scope/score')

        # Create Score
        response = self.client.post(
            self.scores_endpoint,
            data=json.dumps({
                "timestamp": self.early_timestamp,
                "scoreGiven": 21,
                "scoreMaximum": 100,
                "comment": "This is exceptional work.",
                "activityProgress": LtiAgsScore.INITIALIZED,
                "gradingProgress": LtiAgsScore.NOT_READY,
                "userId": self.primary_user_id
            }),
            content_type="application/vnd.ims.lis.v1.score+json",
        )

        self.assertEqual(LtiAgsScore.objects.all().count(), 1)
        self.assertEqual(response.status_code, 201)

        # Create 2nd Score with same timestamp, but different data
        response = self.client.post(
            self.scores_endpoint,
            data=json.dumps({
                "timestamp": self.early_timestamp,
                "scoreGiven": 83,
                "scoreMaximum": 100,
                "comment": "This is exceptional work.",
                "activityProgress": LtiAgsScore.COMPLETED,
                "gradingProgress": LtiAgsScore.FULLY_GRADED,
                "userId": self.secondary_user_id
            }),
            content_type="application/vnd.ims.lis.v1.score+json",
        )

        self.assertEqual(LtiAgsScore.objects.all().count(), 2)
        self.assertEqual(response.status_code, 201)

        # Check db record contents
        # Score for primary user
        primary_user_score = LtiAgsScore.objects.get(line_item=self.line_item, user_id=self.primary_user_id)
        self.assertEqual(primary_user_score.line_item.id, self.line_item.id)
        self.assertEqual(primary_user_score.timestamp.isoformat(), self.early_timestamp)
        self.assertEqual(primary_user_score.score_given, 21.0)
        self.assertEqual(primary_user_score.score_maximum, 100.0)
        self.assertEqual(primary_user_score.activity_progress, LtiAgsScore.INITIALIZED)
        self.assertEqual(primary_user_score.grading_progress, LtiAgsScore.NOT_READY)
        self.assertEqual(primary_user_score.user_id, self.primary_user_id)

        # Score for secondary user
        secondary_user_score = LtiAgsScore.objects.get(line_item=self.line_item, user_id=self.secondary_user_id)
        self.assertEqual(secondary_user_score.line_item.id, self.line_item.id)
        self.assertEqual(secondary_user_score.timestamp.isoformat(), self.early_timestamp)
        self.assertEqual(secondary_user_score.score_given, 83.0)
        self.assertEqual(secondary_user_score.score_maximum, 100.0)
        self.assertEqual(secondary_user_score.activity_progress, LtiAgsScore.COMPLETED)
        self.assertEqual(secondary_user_score.grading_progress, LtiAgsScore.FULLY_GRADED)
        self.assertEqual(secondary_user_score.user_id, self.secondary_user_id)

    def test_create_multiple_scores_with_later_timestamp(self):
        """
        Test the LTI AGS LineItem Score updating with a later timestamp updates the record.
        """
        self._set_lti_token('https://purl.imsglobal.org/spec/lti-ags/scope/score')

        # Create Score
        response = self.client.post(
            self.scores_endpoint,
            data=json.dumps({
                "timestamp": self.early_timestamp,
                "scoreGiven": 21,
                "scoreMaximum": 100,
                "comment": "This is exceptional work.",
                "activityProgress": LtiAgsScore.INITIALIZED,
                "gradingProgress": LtiAgsScore.NOT_READY,
                "userId": self.primary_user_id
            }),
            content_type="application/vnd.ims.lis.v1.score+json",
        )

        self.assertEqual(LtiAgsScore.objects.all().count(), 1)
        self.assertEqual(response.status_code, 201)

        # Create 2nd Score with same timestamp, but different data
        response = self.client.post(
            self.scores_endpoint,
            data=json.dumps({
                "timestamp": self.late_timestamp,
                "scoreGiven": 83,
                "scoreMaximum": 100,
                "comment": "This is exceptional work.",
                "activityProgress": LtiAgsScore.COMPLETED,
                "gradingProgress": LtiAgsScore.FULLY_GRADED,
                "userId": self.primary_user_id
            }),
            content_type="application/vnd.ims.lis.v1.score+json",
        )

        self.assertEqual(LtiAgsScore.objects.all().count(), 1)
        self.assertEqual(response.status_code, 201)

        # Check db record contents
        score = LtiAgsScore.objects.get(line_item=self.line_item, user_id=self.primary_user_id)
        self.assertEqual(score.line_item.id, self.line_item.id)
        self.assertEqual(score.timestamp.isoformat(), self.late_timestamp)
        self.assertEqual(score.score_given, 83.0)
        self.assertEqual(score.score_maximum, 100.0)
        self.assertEqual(score.activity_progress, LtiAgsScore.COMPLETED)
        self.assertEqual(score.grading_progress, LtiAgsScore.FULLY_GRADED)
        self.assertEqual(score.user_id, self.primary_user_id)

    def test_create_multiple_scores_with_same_timestamp(self):
        """
        Test the LTI AGS LineItem Score updating with an existing timestamp fails to update the record.
        """
        self._set_lti_token('https://purl.imsglobal.org/spec/lti-ags/scope/score')

        # Create Score
        response = self.client.post(
            self.scores_endpoint,
            data=json.dumps({
                "timestamp": self.early_timestamp,
                "scoreGiven": 21,
                "scoreMaximum": 100,
                "comment": "This is exceptional work.",
                "activityProgress": LtiAgsScore.INITIALIZED,
                "gradingProgress": LtiAgsScore.NOT_READY,
                "userId": self.primary_user_id
            }),
            content_type="application/vnd.ims.lis.v1.score+json",
        )

        self.assertEqual(LtiAgsScore.objects.all().count(), 1)
        self.assertEqual(response.status_code, 201)

        # Create 2nd Score with same timestamp, but different data
        response = self.client.post(
            self.scores_endpoint,
            data=json.dumps({
                "timestamp": self.early_timestamp,
                "scoreGiven": 83,
                "scoreMaximum": 100,
                "comment": "This is exceptional work.",
                "activityProgress": LtiAgsScore.COMPLETED,
                "gradingProgress": LtiAgsScore.FULLY_GRADED,
                "userId": self.primary_user_id
            }),
            content_type="application/vnd.ims.lis.v1.score+json",
        )

        self.assertEqual(LtiAgsScore.objects.all().count(), 1)
        self.assertEqual(response.status_code, 400)

        # Check db record contents are the original data
        score = LtiAgsScore.objects.get(line_item=self.line_item, user_id=self.primary_user_id)
        self.assertEqual(score.line_item.id, self.line_item.id)
        self.assertEqual(score.timestamp.isoformat(), self.early_timestamp)
        self.assertEqual(score.score_given, 21.0)
        self.assertEqual(score.score_maximum, 100.0)
        self.assertEqual(score.activity_progress, LtiAgsScore.INITIALIZED)
        self.assertEqual(score.grading_progress, LtiAgsScore.NOT_READY)
        self.assertEqual(score.user_id, self.primary_user_id)

    def test_create_second_score_with_earlier_timestamp(self):
        """
        Test the LTI AGS LineItem Score updating with an earlier timestamp fails to update the record.
        """
        self._set_lti_token('https://purl.imsglobal.org/spec/lti-ags/scope/score')

        # Create Score
        response = self.client.post(
            self.scores_endpoint,
            data=json.dumps({
                "timestamp": self.late_timestamp,
                "scoreGiven": 21,
                "scoreMaximum": 100,
                "comment": "This is exceptional work.",
                "activityProgress": LtiAgsScore.INITIALIZED,
                "gradingProgress": LtiAgsScore.NOT_READY,
                "userId": self.primary_user_id
            }),
            content_type="application/vnd.ims.lis.v1.score+json",
        )

        self.assertEqual(LtiAgsScore.objects.all().count(), 1)
        self.assertEqual(response.status_code, 201)

        # Create 2nd Score with earlier timestamp, and different data
        response = self.client.post(
            self.scores_endpoint,
            data=json.dumps({
                "timestamp": self.early_timestamp,
                "scoreGiven": 83,
                "scoreMaximum": 100,
                "comment": "This is exceptional work.",
                "activityProgress": LtiAgsScore.COMPLETED,
                "gradingProgress": LtiAgsScore.FULLY_GRADED,
                "userId": self.primary_user_id
            }),
            content_type="application/vnd.ims.lis.v1.score+json",
        )

        self.assertEqual(LtiAgsScore.objects.all().count(), 1)
        self.assertEqual(response.status_code, 400)

        # Check db record contents are the original data
        score = LtiAgsScore.objects.get(line_item=self.line_item, user_id=self.primary_user_id)
        self.assertEqual(score.line_item.id, self.line_item.id)
        self.assertEqual(score.timestamp.isoformat(), self.late_timestamp)
        self.assertEqual(score.score_given, 21.0)
        self.assertEqual(score.score_maximum, 100.0)
        self.assertEqual(score.activity_progress, LtiAgsScore.INITIALIZED)
        self.assertEqual(score.grading_progress, LtiAgsScore.NOT_READY)
        self.assertEqual(score.user_id, self.primary_user_id)

    def test_create_score_with_missing_score_maximum(self):
        """
        Test invalid request with missing scoreMaximum.
        """
        self._set_lti_token('https://purl.imsglobal.org/spec/lti-ags/scope/score')

        # Create invalid Score
        response = self.client.post(
            self.scores_endpoint,
            data=json.dumps({
                "timestamp": self.late_timestamp,
                "scoreGiven": 21,
                "comment": "This is exceptional work.",
                "activityProgress": LtiAgsScore.INITIALIZED,
                "gradingProgress": LtiAgsScore.NOT_READY,
                "userId": self.primary_user_id
            }),
            content_type="application/vnd.ims.lis.v1.score+json",
        )

        self.assertEqual(LtiAgsScore.objects.all().count(), 0)
        self.assertEqual(response.status_code, 400)
        assert 'score_maximum' in response.data.keys()

    def test_erase_score(self):
        """
        Test erasing LTI AGS Scores by omitting scoreGiven and scoreMaximum.
        """
        # Have a score already existing
        LtiAgsScore.objects.create(
            line_item=self.line_item,
            timestamp=self.early_timestamp,
            score_given=25,
            score_maximum=100,
            comment="This is exceptional work.",
            activity_progress=LtiAgsScore.COMPLETED,
            grading_progress=LtiAgsScore.FULLY_GRADED,
            user_id=self.primary_user_id
        )

        self._set_lti_token('https://purl.imsglobal.org/spec/lti-ags/scope/score')

        # Erase Score
        response = self.client.post(
            self.scores_endpoint,
            data=json.dumps({
                "timestamp": self.late_timestamp,
                "comment": None,
                "activityProgress": LtiAgsScore.INITIALIZED,
                "gradingProgress": LtiAgsScore.NOT_READY,
                "userId": self.primary_user_id
            }),
            content_type="application/vnd.ims.lis.v1.score+json",
        )

        self.assertEqual(LtiAgsScore.objects.all().count(), 1)
        self.assertEqual(response.status_code, 201)

        # The serializer replaces `+00:00` with `Z`
        response_timestamp = self.late_timestamp.replace('+00:00', 'Z')
        self.assertEqual(
            response.data,
            {
                "timestamp": response_timestamp,
                "scoreGiven": None,
                "scoreMaximum": None,
                "comment": None,
                "activityProgress": LtiAgsScore.INITIALIZED,
                "gradingProgress": LtiAgsScore.NOT_READY,
                "userId": self.primary_user_id
            }
        )

        # Check db record contents (because we don't delete the record, just blank it out)
        score = LtiAgsScore.objects.get(line_item=self.line_item, user_id=self.primary_user_id)
        self.assertEqual(score.line_item.id, self.line_item.id)
        self.assertEqual(score.timestamp.isoformat(), self.late_timestamp)
        self.assertEqual(score.score_given, None)
        self.assertEqual(score.score_maximum, None)
        self.assertEqual(score.activity_progress, LtiAgsScore.INITIALIZED)
        self.assertEqual(score.grading_progress, LtiAgsScore.NOT_READY)
        self.assertEqual(score.user_id, self.primary_user_id)


class LtiAgsViewSetResultsTests(LtiAgsLineItemViewSetTestCase):
    """
    Test `LtiAgsLineItemViewset` Results retrieval requests/responses.
    """

    def setUp(self):
        super().setUp()

        # Create LineItem
        self.line_item = LtiAgsLineItem.objects.create(
            lti_configuration=self.lti_config,
            resource_id="test",
            resource_link_id=self.xblock.location,
            label="test label",
            score_maximum=100
        )

        self.early_timestamp = "2020-01-01T18:54:36.736000+00:00"
        self.middle_timestamp = "2021-01-01T18:54:36.736000+00:00"
        self.late_timestamp = "2022-01-01T18:54:36.736000+00:00"

        # Create Scores
        self.primary_user_id = "primary"
        LtiAgsScore.objects.create(
            line_item=self.line_item,
            timestamp=self.late_timestamp,
            score_given=83,
            score_maximum=100,
            comment="This is exceptional work.",
            activity_progress=LtiAgsScore.COMPLETED,
            grading_progress=LtiAgsScore.FULLY_GRADED,
            user_id=self.primary_user_id
        )

        self.secondary_user_id = "secondary"
        LtiAgsScore.objects.create(
            line_item=self.line_item,
            timestamp=self.middle_timestamp,
            score_given=25,
            score_maximum=100,
            comment="This is not great work.",
            activity_progress=LtiAgsScore.COMPLETED,
            grading_progress=LtiAgsScore.FULLY_GRADED,
            user_id=self.secondary_user_id
        )

        self.empty_score_user_id = "empty_score_user"
        LtiAgsScore.objects.create(
            line_item=self.line_item,
            timestamp=self.early_timestamp,
            score_given=None,
            score_maximum=None,
            comment=None,
            activity_progress=LtiAgsScore.INITIALIZED,
            grading_progress=LtiAgsScore.NOT_READY,
            user_id=self.empty_score_user_id
        )

        # LineItem endpoint
        self.lineitem_endpoint = reverse(
            'lti_consumer:lti-ags-view-detail',
            kwargs={
                "lti_config_id": self.lti_config.id,
                "pk": self.line_item.id
            }
        )

        # Results endpoint
        self.results_endpoint = reverse(
            'lti_consumer:lti-ags-view-results',
            kwargs={
                "lti_config_id": self.lti_config.id,
                "pk": self.line_item.id
            }
        )

    def test_retrieve_results(self):
        """
        Test the LTI AGS LineItem Score Creation.
        """
        self._set_lti_token('https://purl.imsglobal.org/spec/lti-ags/scope/result.readonly')

        # Create Score
        response = self.client.get(self.results_endpoint)

        self.assertEqual(response.status_code, 200)

        # There should be 2 results (not include the empty score user's result)
        self.assertEqual(len(response.data), 2)

        # Check the data
        primary_user_results_endpoint = reverse(
            'lti_consumer:lti-ags-view-results',
            kwargs={
                "lti_config_id": self.lti_config.id,
                "pk": self.line_item.id,
                "user_id": self.primary_user_id
            }
        )
        secondary_user_results_endpoint = reverse(
            'lti_consumer:lti-ags-view-results',
            kwargs={
                "lti_config_id": self.lti_config.id,
                "pk": self.line_item.id,
                "user_id": self.secondary_user_id
            }
        )
        self.assertEqual(
            [dict(d) for d in response.data],
            [
                {
                    "id": "http://testserver" + primary_user_results_endpoint,
                    "scoreOf": "http://testserver" + self.lineitem_endpoint,
                    "userId": self.primary_user_id,
                    "resultScore": 83.0,
                    "resultMaximum": 100.0,
                    "comment": "This is exceptional work."
                },
                {
                    "id": "http://testserver" + secondary_user_results_endpoint,
                    "scoreOf": "http://testserver" + self.lineitem_endpoint,
                    "userId": self.secondary_user_id,
                    "resultScore": 25.0,
                    "resultMaximum": 100.0,
                    "comment": "This is not great work."
                }
            ]
        )

    def test_retrieve_results_for_user_id(self):
        """
        Test the LTI AGS LineItem Score Creation.
        """
        self._set_lti_token('https://purl.imsglobal.org/spec/lti-ags/scope/result.readonly')

        results_user_endpoint = reverse(
            'lti_consumer:lti-ags-view-results',
            kwargs={
                "lti_config_id": self.lti_config.id,
                "pk": self.line_item.id,
                "user_id": self.secondary_user_id
            }
        )

        # Request results with userId
        response = self.client.get(results_user_endpoint, data={"userId": self.secondary_user_id})

        self.assertEqual(response.status_code, 200)

        # There should be 1 result for that user
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['userId'], self.secondary_user_id)

    def test_retrieve_results_with_limit(self):
        """
        Test the LTI AGS LineItem Score Creation.
        """
        self._set_lti_token('https://purl.imsglobal.org/spec/lti-ags/scope/result.readonly')

        # Request results with limit
        response = self.client.get(self.results_endpoint, data={"limit": 1})

        self.assertEqual(response.status_code, 200)

        # There should be 1 results, and it should be the one with the latest timestamp
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['userId'], self.primary_user_id)