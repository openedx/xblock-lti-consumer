"""
Tests for LTI Names and Role Provisioning Service views.
"""
from unittest.mock import Mock, patch

from Cryptodome.PublicKey import RSA
from rest_framework.reverse import reverse
from rest_framework.test import APITransactionTestCase

from lti_consumer.exceptions import LtiError
from lti_consumer.lti_1p3.constants import (
    LTI_1P3_CONTEXT_ROLE_ADMINISTRATOR,
    LTI_1P3_CONTEXT_ROLE_INSTRUCTOR,
    LTI_1P3_CONTEXT_ROLE_LEARNER,
    LTI_1P3_CONTEXT_ROLE_TEACHING_ASSISTANT,
)
from lti_consumer.lti_xblock import LtiConsumerXBlock
from lti_consumer.models import LtiConfiguration
from lti_consumer.plugin.views import LtiNrpsContextMembershipViewSet
from lti_consumer.tests.test_utils import TestBaseWithPatch, make_xblock


def generate_mock_members(num, role='student'):
    """
    Helper method to generate mock users.
    """
    members = []

    for i in range(num):
        member = {
            'id': i,
            'username': f'user_{i}',
            'email': f'user{i}@test.com',
            'name': f'User {i}'
        }

        if role == 'student':
            member.update({
                'roles': ['student'],
                'id': 1000 + i
            })
        elif role == 'instructor':
            member.update({
                'roles': ['instructor'],
                'id': 2000 + i
            })
        elif role == 'staff':
            member.update({
                'roles': ['staff'],
                'id': 3000 + i
            })

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
            'exception': False
        }
    """
    members = []
    raise_exception = False

    # generate mock users based on config
    if isinstance(config, dict):
        if config.get('exception'):
            raise_exception = True
        else:
            members += generate_mock_members(config.get('student', 0), role='student')
            members += generate_mock_members(config.get('instructor', 0), role='instructor')
            members += generate_mock_members(config.get('staff', 0), role='staff')

    def _get_memberships(course_key):  # pylint: disable=unused-argument
        """
        Returns mock data or raises exception based on `config`
        """
        # simulate enrollment limit exception
        if raise_exception:
            raise LtiError
        return {member['id']: member for member in members}

    return _get_memberships


class LtiNrpsTestCase(APITransactionTestCase, TestBaseWithPatch):  # noqa: F821
    """
    Test LtiNrpsViewSet actions
    """

    def setUp(self):
        super().setUp()

        # Create custom LTI Block
        rsa_key = RSA.generate(2048)
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

        # Create configuration
        self.lti_config = LtiConfiguration.objects.create(
            location=self.xblock.scope_ids.usage_id,
            version=LtiConfiguration.LTI_1P3,
        )

        # Patch internal method to avoid calls to modulestore
        patcher = patch(
            'lti_consumer.plugin.compat.load_enough_xblock',
        )
        self.addCleanup(patcher.stop)
        self._load_block_patch = patcher.start()
        self._load_block_patch.return_value = self.xblock

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
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {token}"
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

    @patch('lti_consumer.plugin.views.get_lti_pii_sharing_state_for_course', Mock(return_value=False))
    @patch(
        'lti_consumer.plugin.views.compat.get_course_members',
        Mock(side_effect=patch_get_memberships()),
    )
    def test_token_with_correct_scope(self):
        """
        Test if context membership returns correct response when token has correct scope
        """
        self._set_lti_token('https://purl.imsglobal.org/spec/lti-nrps/scope/contextmembership.readonly')
        response = self.client.get(self.context_membership_endpoint)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['content-type'], 'application/vnd.ims.lti-nrps.v2.membershipcontainer+json')

    @patch('lti_consumer.plugin.views.get_lti_pii_sharing_state_for_course', return_value=False)
    @patch(
        'lti_consumer.plugin.views.compat.get_course_members',
        Mock(side_effect=patch_get_memberships({
            'student': 4
        })),
    )
    def test_get_without_pii(self, expose_pii_fields_patcher):
        """
        Test context membership endpoint response structure with PII not exposed.
        """
        self._set_lti_token('https://purl.imsglobal.org/spec/lti-nrps/scope/contextmembership.readonly')
        response = self.client.get(self.context_membership_endpoint)
        self.assertEqual(response.data['id'], f'http://testserver{self.context_membership_endpoint}')
        self.assertEqual(len(response.data['members']), 4)
        self.assertEqual(response.has_header('Link'), False)

        expose_pii_fields_patcher.assert_called()

        # name & email should not be exposed.
        member_fields = response.data['members'][0].keys()
        self.assertIn('user_id', member_fields)
        self.assertIn('roles', member_fields)
        self.assertIn('status', member_fields)
        self.assertNotIn('email', member_fields)
        self.assertNotIn('name', member_fields)

    @patch('lti_consumer.plugin.views.get_lti_pii_sharing_state_for_course', return_value=True)
    @patch(
        'lti_consumer.plugin.views.compat.get_course_members',
        Mock(side_effect=patch_get_memberships({
            'student': 4
        })),
    )
    def test_get_with_pii(self, expose_pii_fields_patcher):
        """
        Test context membership endpoint response structure with PII exposed.
        """
        self._set_lti_token('https://purl.imsglobal.org/spec/lti-nrps/scope/contextmembership.readonly')
        response = self.client.get(self.context_membership_endpoint)

        self.assertEqual(response.data['id'], f'http://testserver{self.context_membership_endpoint}')
        self.assertEqual(len(response.data['members']), 4)
        self.assertEqual(response.has_header('Link'), False)

        expose_pii_fields_patcher.assert_called()

        # name & email should be present along with user_id, roles etc.
        member_fields = response.data['members'][0].keys()
        self.assertIn('user_id', member_fields)
        self.assertIn('roles', member_fields)
        self.assertIn('status', member_fields)
        self.assertIn('email', member_fields)
        self.assertIn('name', member_fields)

    @patch('lti_consumer.plugin.views.get_lti_pii_sharing_state_for_course', return_value=False)
    @patch(
        'lti_consumer.plugin.views.compat.get_course_members',
        Mock(side_effect=patch_get_memberships({
            'student': 1,
            'instructor': 1,
            'staff': 1,
        })),
    )
    def test_get_membership_roles_mapping(self, expose_pii_fields_patcher):
        """
        Test context membership endpoint returns mapped LTI context role URIs.
        """
        self._set_lti_token('https://purl.imsglobal.org/spec/lti-nrps/scope/contextmembership.readonly')
        response = self.client.get(self.context_membership_endpoint)

        expose_pii_fields_patcher.assert_called()
        self.assertEqual(len(response.data['members']), 3)

        actual_roles = [set(member['roles']) for member in response.data['members']]

        self.assertIn(
            set(LTI_1P3_CONTEXT_ROLE_LEARNER),
            actual_roles,
        )
        self.assertIn(
            set(LTI_1P3_CONTEXT_ROLE_INSTRUCTOR),
            actual_roles,
        )
        self.assertIn(
            set(LTI_1P3_CONTEXT_ROLE_ADMINISTRATOR),
            actual_roles,
        )

    @patch('lti_consumer.plugin.views.get_lti_pii_sharing_state_for_course', return_value=False)
    @patch(
        'lti_consumer.plugin.views.compat.get_course_members',
        Mock(side_effect=patch_get_memberships({
            'student': 1,
        })),
    )
    @patch('lti_consumer.plugin.compat.get_forum_role_model')
    def test_get_membership_roles_mapping_includes_forum_roles(
        self,
        get_forum_role_model_patcher,
        expose_pii_fields_patcher,
    ):
        """
        Test context membership endpoint includes mapped forum roles.
        """
        fake_role = Mock()
        fake_role.objects.filter.return_value.values_list.return_value = [(1000, 'Community TA')]
        get_forum_role_model_patcher.return_value = fake_role

        self._set_lti_token('https://purl.imsglobal.org/spec/lti-nrps/scope/contextmembership.readonly')
        response = self.client.get(self.context_membership_endpoint)

        expose_pii_fields_patcher.assert_called()
        fake_role.objects.filter.assert_called_once()
        self.assertEqual(len(response.data['members']), 1)
        self.assertEqual(
            set(response.data['members'][0]['roles']),
            set(LTI_1P3_CONTEXT_ROLE_LEARNER + LTI_1P3_CONTEXT_ROLE_TEACHING_ASSISTANT),
        )

    @patch('lti_consumer.plugin.views.get_lti_pii_sharing_state_for_course', Mock(return_value=False))
    @patch(
        'lti_consumer.plugin.views.compat.get_course_members',
        Mock(side_effect=patch_get_memberships({
            'exception': True
        })),
    )
    def test_enrollment_limit_gate(self):
        """
        Test if number of enrolled user is larger than the limit, api returns 404 response.
        """
        self._set_lti_token('https://purl.imsglobal.org/spec/lti-nrps/scope/contextmembership.readonly')

        response = self.client.get(self.context_membership_endpoint)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data['error'], 'above_response_limit')

    @patch('lti_consumer.plugin.views.get_lti_pii_sharing_state_for_course', Mock(return_value=False))
    @patch(
        'lti_consumer.plugin.views.compat.get_course_members',
        Mock(side_effect=patch_get_memberships({
            'student': 4
        })),
    )
    def test_limit_pagination_returns_bounded_page(self):
        """
        Test that when limit is provided, the response contains at most 'limit' members
        and includes a Link header with rel="next" when more members remain.
        """
        self._set_lti_token('https://purl.imsglobal.org/spec/lti-nrps/scope/contextmembership.readonly')
        response = self.client.get(self.context_membership_endpoint, {'limit': 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['members']), 2)
        self.assertTrue(response.has_header('Link'))
        self.assertIn('rel="next"', response['Link'])

    @patch('lti_consumer.plugin.views.get_lti_pii_sharing_state_for_course', Mock(return_value=False))
    @patch(
        'lti_consumer.plugin.views.compat.get_course_members',
        Mock(side_effect=patch_get_memberships({
            'student': 4
        })),
    )
    def test_limit_pagination_next_url_has_limit_and_page(self):
        """
        Test that the Link header's next URL contains the same limit and page=2
        and preserves unrelated query params.
        """
        self._set_lti_token('https://purl.imsglobal.org/spec/lti-nrps/scope/contextmembership.readonly')
        response = self.client.get(
            self.context_membership_endpoint,
            {'limit': 2, 'role': 'foo'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.has_header('Link'))

        link_header = response['Link']
        parsed_links = self._parse_link_headers(link_header)
        self.assertIn('next', parsed_links)

        next_url = parsed_links['next']
        self.assertIn('limit=2', next_url)
        self.assertIn('page=2', next_url)
        self.assertIn('role=foo', next_url)

    @patch('lti_consumer.plugin.views.get_lti_pii_sharing_state_for_course', Mock(return_value=False))
    @patch(
        'lti_consumer.plugin.views.compat.get_course_members',
        Mock(side_effect=patch_get_memberships({
            'student': 4
        })),
    )
    def test_limit_pagination_last_page_omits_next(self):
        """
        Test that on the last page, no Link header with rel="next" is present.
        """
        self._set_lti_token('https://purl.imsglobal.org/spec/lti-nrps/scope/contextmembership.readonly')
        response = self.client.get(self.context_membership_endpoint, {'limit': 2, 'page': 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['members']), 2)
        self.assertFalse(response.has_header('Link'))

    @patch('lti_consumer.plugin.views.get_lti_pii_sharing_state_for_course', Mock(return_value=False))
    @patch(
        'lti_consumer.plugin.views.compat.get_course_members',
        Mock(side_effect=patch_get_memberships({
            'student': 4
        })),
    )
    def test_limit_pagination_single_remaining(self):
        """
        Test that when limit=3 and page=2, only 1 member is returned and no next Link.
        """
        self._set_lti_token('https://purl.imsglobal.org/spec/lti-nrps/scope/contextmembership.readonly')
        response = self.client.get(self.context_membership_endpoint, {'limit': 3, 'page': 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['members']), 1)
        self.assertFalse(response.has_header('Link'))

    @patch('lti_consumer.plugin.views.get_lti_pii_sharing_state_for_course', Mock(return_value=False))
    @patch(
        'lti_consumer.plugin.views.compat.get_course_members',
        Mock(side_effect=patch_get_memberships({
            'student': 4
        })),
    )
    def test_invalid_limit_returns_all_members(self):
        """
        Test that an invalid limit (non-positive or non-integer) returns all members
        without pagination.
        """
        self._set_lti_token('https://purl.imsglobal.org/spec/lti-nrps/scope/contextmembership.readonly')

        # Test with limit=0
        response = self.client.get(self.context_membership_endpoint, {'limit': 0})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['members']), 4)
        self.assertFalse(response.has_header('Link'))

        # Test with negative limit
        response = self.client.get(self.context_membership_endpoint, {'limit': -5})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['members']), 4)
        self.assertFalse(response.has_header('Link'))

        # Test with non-integer limit
        response = self.client.get(self.context_membership_endpoint, {'limit': 'abc'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['members']), 4)
        self.assertFalse(response.has_header('Link'))

    @patch('lti_consumer.plugin.views.get_lti_pii_sharing_state_for_course', Mock(return_value=False))
    @patch(
        'lti_consumer.plugin.views.compat.get_course_members',
        Mock(side_effect=patch_get_memberships({
            'student': 4
        })),
    )
    def test_invalid_page_defaults_to_one(self):
        """
        Test that an invalid page value defaults to page 1.
        """
        self._set_lti_token('https://purl.imsglobal.org/spec/lti-nrps/scope/contextmembership.readonly')

        # Test with page=0
        response = self.client.get(self.context_membership_endpoint, {'limit': 2, 'page': 0})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['members']), 2)
        self.assertTrue(response.has_header('Link'))

        # Test with non-integer page
        response = self.client.get(self.context_membership_endpoint, {'limit': 2, 'page': 'abc'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['members']), 2)
        self.assertTrue(response.has_header('Link'))

    @patch('lti_consumer.plugin.views.get_lti_pii_sharing_state_for_course', Mock(return_value=False))
    def test_pagination_sorts_by_id_for_stable_pages(self):
        """Test pagination stays stable when member insertion order changes between requests.

        The two page requests return the same members in opposite dictionary orders;
        sorting by ID should still produce every member exactly once, without gaps or
        duplicates.
        """
        members = [{'id': 2000 + i, 'username': f'user_{2000 + i}', 'roles': ['student']} for i in range(4)]
        insertion_orders = [members, list(reversed(members))]

        def get_members(_course_key):
            return {member['id']: member for member in insertion_orders.pop(0)}

        def attach_external_ids(data):
            for member in data.values():
                member['external_id'] = str(member['id'])

        self._set_lti_token('https://purl.imsglobal.org/spec/lti-nrps/scope/contextmembership.readonly')

        with patch('lti_consumer.plugin.views.compat.get_course_members', side_effect=get_members), patch.object(
            LtiNrpsContextMembershipViewSet,
            'attach_external_user_ids',
            side_effect=attach_external_ids,
        ):
            page_ids = []
            for page in (1, 2):
                response = self.client.get(
                    self.context_membership_endpoint,
                    {'limit': 2, 'page': page},
                )
                self.assertEqual(response.status_code, 200)
                page_ids.extend(member['user_id'] for member in response.data['members'])

        self.assertEqual(page_ids, ['2000', '2001', '2002', '2003'])
        self.assertEqual(len(page_ids), len(set(page_ids)))
