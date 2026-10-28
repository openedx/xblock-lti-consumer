"""
Tests for reusable LTI configuration permissions.
"""

import ddt
from django.contrib.auth import get_user_model
from django.test import TestCase

from lti_consumer.authz import demo
from lti_consumer.authz.permissions import (
    CONFIGURATION_ACTIONS,
    INSTANCE_CONTEXT,
    VIEW_CONFIGURATION,
    get_scopes_for_context,
    org_context,
    unassign_lti_manager,
    user_has_configuration_permission,
)


@ddt.ddt
class TestGetScopesForContext(TestCase):
    """
    Tests for mapping a configuration's context to authz scopes.
    """

    @ddt.data(
        ("course-v1:MIT+W+2026", ["course-v1:MIT+W+2026"]),
        ("lib:MIT:L", ["lib:MIT:L"]),
        (org_context("MIT"), ["course-v1:MIT+*", "lib:MIT:*"]),
        (INSTANCE_CONTEXT, ["course-v1:*", "lib:*"]),
        (None, []),
        ("", []),
    )
    @ddt.unpack
    def test_scopes(self, context_key, expected):
        self.assertEqual(get_scopes_for_context(context_key), expected)


@ddt.ddt
class TestUserHasConfigurationPermission(TestCase):
    """
    Check every user, action and configuration in the demo data against the expected table.
    """

    def setUp(self):
        super().setUp()
        self.configs = demo.seed()

    @ddt.data(*demo.EXPECTED)
    def test_expected_permissions(self, username):
        user = get_user_model().objects.get(username=username)
        actual = {
            action: {
                name for name, config in self.configs.items()
                if user_has_configuration_permission(user, permission, config)
            }
            for action, permission in CONFIGURATION_ACTIONS.items()
        }
        self.assertEqual(actual, demo.EXPECTED[username])

    def test_unassign_lti_manager_removes_both_scopes(self):
        """
        Revoking an org LTI Manager removes both the course and library assignments.
        """
        user = get_user_model().objects.get(username="user2")
        unassign_lti_manager("user2", org_context("MIT"))

        for name in ("A", "B", "F"):
            self.assertFalse(user_has_configuration_permission(user, VIEW_CONFIGURATION, self.configs[name]))

    def test_user_without_roles_has_no_permissions(self):
        user = get_user_model().objects.create(username="nobody")
        for config in self.configs.values():
            for permission in CONFIGURATION_ACTIONS.values():
                self.assertFalse(user_has_configuration_permission(user, permission, config))
