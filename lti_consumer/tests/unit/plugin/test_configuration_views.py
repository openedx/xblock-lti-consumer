"""
Tests for the reusable LTI configuration API.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from lti_consumer.authz import demo


class TestReusableLtiConfigurationViewSet(TestCase):
    """
    The API applies the context permissions: course staff on run W (user1) can
    edit config A, can only view org config B, and can't see run X's config C.
    """

    def setUp(self):
        super().setUp()
        self.configs = demo.seed()
        self.client = APIClient()
        self.login("user1")

    def login(self, username):
        self.client.force_authenticate(get_user_model().objects.get(username=username))

    def detail_url(self, name):
        return reverse(
            "lti_consumer:lti-configurations-detail",
            kwargs={"passport_id": self.configs[name].passport_id},
        )

    def permissions_url(self, name):
        return reverse(
            "lti_consumer:lti-configurations-permissions",
            kwargs={"passport_id": self.configs[name].passport_id},
        )

    def test_retrieve_returns_minimal_view(self):
        response = self.client.get(self.detail_url("A"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "passport_id": str(self.configs["A"].passport_id),
            "name": "Config A",
            "context_key": demo.COURSE_W,
            "launch_domain": "tool-a.example.com",
        })

    def test_retrieve_without_view_is_forbidden(self):
        response = self.client.get(self.detail_url("C"))

        self.assertEqual(response.status_code, 403)

    def test_update_with_edit(self):
        response = self.client.patch(self.detail_url("A"), {"name": "Renamed"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.configs["A"].refresh_from_db()
        self.assertEqual(self.configs["A"].name, "Renamed")

    def test_update_with_only_view_is_forbidden(self):
        response = self.client.patch(self.detail_url("B"), {"name": "Renamed"}, format="json")

        self.assertEqual(response.status_code, 403)
        self.configs["B"].refresh_from_db()
        self.assertEqual(self.configs["B"].name, "Config B")

    def test_org_lti_manager_can_update_org_configuration(self):
        self.login("user2")

        response = self.client.patch(self.detail_url("B"), {"name": "Renamed"}, format="json")

        self.assertEqual(response.status_code, 200)

    def test_context_cannot_be_changed(self):
        response = self.client.patch(self.detail_url("A"), {"context_key": demo.COURSE_X}, format="json")

        self.assertEqual(response.status_code, 200)
        self.configs["A"].refresh_from_db()
        self.assertEqual(self.configs["A"].context_key, demo.COURSE_W)

    def test_permissions(self):
        response = self.client.get(self.permissions_url("B"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"view": True, "create": False, "edit": False, "delete": False})

    def test_permissions_without_any_access(self):
        response = self.client.get(self.permissions_url("C"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"view": False, "create": False, "edit": False, "delete": False})

    def test_anonymous_user_is_rejected(self):
        self.client.force_authenticate(None)

        for url in (self.detail_url("A"), self.permissions_url("A")):
            self.assertIn(self.client.get(url).status_code, (401, 403))
