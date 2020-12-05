"""
Tests for LTI Names and Role Provisioning Service views.
"""
from django.conf import settings
from mock import patch, PropertyMock
from Cryptodome.PublicKey import RSA
from jwkest.jwk import RSAKey
from rest_framework.test import APITransactionTestCase
from django.core.paginator import Paginator
from rest_framework.reverse import reverse

from lti_consumer.lti_xblock import LtiConsumerXBlock
from lti_consumer.models import LtiConfiguration
from lti_consumer.tests.unit.test_utils import make_xblock


def generate_mock_members(num, role='student'):
    """
    Helper method to generate mock users.
    """
    members = []

    for i in range(num):
        member = {
            'id': i,
            'username': 'user_{}'.format(i),
            'email': 'user{}@test.com'.format(i),
            'profile': {
                'name': 'User {}'.format(i),
                'profile_image': {
                    'has_image': True,
                    'image_url_small': '/small/profile/image'
                }
            },
            'enrollments': [],
            'course_access_roles': [],
        }

        if role == 'student':
            member['enrollments'] = [{
                'mode': 'audit'
            }]
        elif role == 'instructor':
            member['course_access_roles'] = [{
                'role': 'instructor'
            }]
        elif role == 'staff':
            member['course_access_roles'] = [{
                'role': 'stuff'
            }]
        members.append(member)

    return members


class MockExternalId:
    """
    Mock ExternalID model
    """
    external_user_id = 'external-id'


class ExternalIDMapping(dict):
    """
    Mock user id to external id mapping
    """

    def __getitem__(self, key):
        """
        For any user id return external user id
        """
        return MockExternalId()


def patch_get_memberships(config=None):
    """
    Patch for get_course_membership function

    Args:
        config: a dict containing number of mock user to generate for each user role - ex:
        {
            'student': 4,
            'instructor': 5,
            'staff': 4,
        }
    """
    members = []

    # generate mock users based on config
    if isinstance(config, dict):
        members += generate_mock_members(config.get('student', 0), role='student')
        members += generate_mock_members(config.get('instructor', 0), role='instructor')
        members += generate_mock_members(config.get('staff', 0), role='staff')

    def _get_memberships(
        course_key,
        page=1,
        access_roles=None,
        include_students=True,
        per_page=settings.REST_FRAMEWORK['PAGE_SIZE']
    ):  # pylint: disable=unused-argument

        paginator = Paginator(members, per_page)
        return {
            'count': paginator.count,
            'num_pages': paginator.num_pages,
            'current_page': page,
            'result': list(paginator.page(page))
        }

    return _get_memberships


class LtiNrpsTestCase(APITransactionTestCase):
    """
    Test LtiNrpsViewSet actions
    """

    def setUp(self):
        super().setUp()

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
            # Intentionally using the same key for tool key to
            # allow using signing methods and make testing easier.
            'lti_1p3_tool_public_key': self.public_key,

            # LTI NRPS related attributes
            'lti_1p3_enable_nrps': True
        }

        self.xblock = make_xblock('lti_consumer', LtiConsumerXBlock, self.xblock_attributes)

        # Set dummy location so that UsageKey lookup is valid
        self.xblock.location = 'block-v1:course+test+2020+type@problem+block@test'

        # Create configuration
        self.lti_config = LtiConfiguration.objects.create(
            location=str(self.xblock.location),
            version=LtiConfiguration.LTI_1P3,
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

        self.context_membership_endpoint = reverse(
            'lti_consumer:lti-nrps-memberships-view-list',
            kwargs={
                "lti_config_id": self.lti_config.id
            }
        )

        batch_external_id_patcher = patch(
            'lti_consumer.plugin.views.compat.batch_get_or_create_externalids',
            return_value=ExternalIDMapping()
        )

        self._batch_external_id_patcher = batch_external_id_patcher.start()

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

    def _parse_link_headers(self, links):
        """
        Helper method to parse Link headers.
        For example given string -
            '<http://example.com/next>; rel="next", <http://example.com/prev>; rel="prev"'
        This method will return a dictionary containing-
            {
                'next': 'http://example.com/next',
                'pref': 'http://example.com/prev',
            }
        """
        result = {}
        for link in links.split(','):
            link_part, rel_part = link.split(';')
            link_part = link_part[1:][:-1].strip()
            rel_part = rel_part.replace('rel="', '').replace('"', '').strip()
            result[rel_part] = link_part
        return result


class LtiNrpsContextMembershipViewsetTestCase(LtiNrpsTestCase):
    """
    Test LTI-NRPS Context Membership Endpoint
    """

    def test_unauthenticated_request(self):
        """
        Test if context membership throws 403 if request is unauthenticated
        """
        response = self.client.get(self.context_membership_endpoint)
        self.assertEqual(response.status_code, 403)

    def test_token_with_incorrect_scope(self):
        """
        Test if context membership throws 403 if token don't have correct scope
        """
        self._set_lti_token()
        response = self.client.get(self.context_membership_endpoint)
        self.assertEqual(response.status_code, 403)

    @patch('lti_consumer.plugin.views.expose_pii_fields', return_value=False)
    @patch(
        'lti_consumer.plugin.views.compat.get_course_members',
        side_effect=patch_get_memberships()
    )
    def test_token_with_correct_scope(self, get_course_members_patcher, expose_pii_fields_patcher):  # pylint: disable=unused-argument
        """
        Test if context membership returns correct response when token has correct scope
        """
        self._set_lti_token('https://purl.imsglobal.org/spec/lti-nrps/scope/contextmembership.readonly')
        response = self.client.get(self.context_membership_endpoint)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['content-type'], 'application/vnd.ims.lti-nrps.v2.membershipcontainer+json')

    @patch('lti_consumer.plugin.views.expose_pii_fields', return_value=False)
    @patch(
        'lti_consumer.plugin.views.compat.get_course_members',
        side_effect=patch_get_memberships({
            'student': 4
        })
    )
    def test_get_without_pii(self, get_course_members_patcher, expose_pii_fields_patcher):  # pylint: disable=unused-argument
        """
        Test context membership endpoint response structure with PII not exposed.
        """
        self._set_lti_token('https://purl.imsglobal.org/spec/lti-nrps/scope/contextmembership.readonly')
        response = self.client.get(self.context_membership_endpoint)
        self.assertEqual(response.data['id'], 'http://testserver{}'.format(self.context_membership_endpoint))
        self.assertEqual(len(response.data['members']), 4)
        self.assertEqual(response.has_header('Link'), False)

        expose_pii_fields_patcher.assert_called()

        # name & email should not be exposed.
        member_fields = response.data['members'][0].keys()
        self.assertEqual(all([
            'user_id' in member_fields,
            'roles' in member_fields,
            'status' in member_fields,
            'email' not in member_fields,
            'name' not in member_fields,
        ]), True)

    @patch('lti_consumer.plugin.views.expose_pii_fields', return_value=True)
    @patch(
        'lti_consumer.plugin.views.compat.get_course_members',
        side_effect=patch_get_memberships({
            'student': 4
        })
    )
    def test_get_with_pii(self, get_course_members_patcher, expose_pii_fields_patcher):  # pylint: disable=unused-argument
        """
        Test context membership endpoint response structure with PII exposed.
        """
        self._set_lti_token('https://purl.imsglobal.org/spec/lti-nrps/scope/contextmembership.readonly')
        response = self.client.get(self.context_membership_endpoint)

        self.assertEqual(response.data['id'], 'http://testserver{}'.format(self.context_membership_endpoint))
        self.assertEqual(len(response.data['members']), 4)
        self.assertEqual(response.has_header('Link'), False)

        expose_pii_fields_patcher.assert_called()

        # name & email should be present along with user_id, roles etc.
        member_fields = response.data['members'][0].keys()
        self.assertEqual(all([
            'user_id' in member_fields,
            'roles' in member_fields,
            'status' in member_fields,
            'email' in member_fields,
            'name' in member_fields,
        ]), True)

    @patch('lti_consumer.plugin.views.expose_pii_fields', return_value=False)
    @patch(
        'lti_consumer.plugin.views.compat.get_course_members',
        side_effect=patch_get_memberships({
            'student': 10,
            'staff': 4,
            'instructor': 1,
        })
    )
    def test_pagination(self, get_course_members_patcher, expose_pii_fields_patcher):  # pylint: disable=unused-argument
        """
        Test that context membership endpoint supports pagination with Link headers.
        """
        self._set_lti_token('https://purl.imsglobal.org/spec/lti-nrps/scope/contextmembership.readonly')
        response = self.client.get(self.context_membership_endpoint)

        self.assertEqual(response.data['id'], 'http://testserver{}'.format(self.context_membership_endpoint))
        self.assertEqual(len(response.data['members']), 10)
        self.assertEqual(response.has_header('Link'), True)

        header_links = self._parse_link_headers(response['Link'])

        response = self.client.get(header_links['next'])
        self.assertEqual(len(response.data['members']), 5)

        header_links = self._parse_link_headers(response['Link'])
        self.assertEqual(header_links.get('next'), None)

    @patch('lti_consumer.plugin.views.expose_pii_fields', return_value=False)
    @patch(
        'lti_consumer.plugin.views.compat.get_course_members',
        side_effect=patch_get_memberships({
            'student': 5
        })
    )
    def test_filter(self, get_course_members_patcher, expose_pii_fields_patcher):  # pylint: disable=unused-argument
        """
        Test if context membership properly builds query with given filter role.
        """
        self._set_lti_token('https://purl.imsglobal.org/spec/lti-nrps/scope/contextmembership.readonly')

        # no filter, all students, instructors & staffs are included by default
        self.client.get('{}'.format(self.context_membership_endpoint))

        call_kwargs = get_course_members_patcher.call_args[1]
        self.assertEqual(call_kwargs['include_students'], True)
        self.assertEqual(call_kwargs['access_roles'], ['instructor', 'staff'])

        # filter only staffs
        self.client.get('{}?role={}'.format(
            self.context_membership_endpoint,
            'http://purl.imsglobal.org/vocab/lis/v2/membership#Administrator'
        ))

        call_kwargs = get_course_members_patcher.call_args[1]
        self.assertEqual(call_kwargs['include_students'], False)
        self.assertEqual(call_kwargs['access_roles'], ['staff'])

        # filter only instructors
        self.client.get('{}?role={}'.format(
            self.context_membership_endpoint,
            'http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor'
        ))

        call_kwargs = get_course_members_patcher.call_args[1]
        self.assertEqual(call_kwargs['include_students'], False)
        self.assertEqual(call_kwargs['access_roles'], ['instructor'])

        # filter only students
        self.client.get('{}?role={}'.format(
            self.context_membership_endpoint,
            'http://purl.imsglobal.org/vocab/lis/v2/membership#Learner'
        ))

        call_kwargs = get_course_members_patcher.call_args[1]
        self.assertEqual(call_kwargs['include_students'], True)
        self.assertEqual(call_kwargs['access_roles'], [])

        # test unsupported filter
        self.client.get('{}?role={}'.format(
            self.context_membership_endpoint,
            'http://purl.imsglobal.org/vocab/lis/v2/membership#ContentDeveloper'
        ))

        call_kwargs = get_course_members_patcher.call_args[1]
        self.assertEqual(call_kwargs['include_students'], False)
        self.assertEqual(call_kwargs['access_roles'], [])

    @patch('lti_consumer.plugin.views.expose_pii_fields', return_value=False)
    @patch(
        'lti_consumer.plugin.views.compat.get_course_members',
        side_effect=patch_get_memberships({
            'student': 15
        })
    )
    @patch('lti_consumer.plugin.views.lti_nrps_enrollment_limit', return_value=10)
    def test_enrollment_limit_gate(self, limit_patcher, get_course_members_patcher, expose_pii_fields_patcher):  # pylint: disable=unused-argument
        """
        Test if number of enrolled user is larger than the limit, api returns 404 response.
        """
        self._set_lti_token('https://purl.imsglobal.org/spec/lti-nrps/scope/contextmembership.readonly')

        response = self.client.get(self.context_membership_endpoint)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data['error'], 'above_response_limit')
