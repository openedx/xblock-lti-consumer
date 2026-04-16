"""
Tests for custom migrations scripts
"""
import importlib
import uuid
from unittest import mock

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class Test0021CreateLti1p3Passport(TransactionTestCase):
    """Exercise data migration 0021 across success and edge-case paths."""

    # MigrationExecutor changes real DB state, so use TransactionTestCase.
    reset_sequences = True

    migrate_from = [("lti_consumer", "0020_lti1p3passport_lticonfiguration_lti_1p3_passport")]
    migrate_to = [("lti_consumer", "0021_create_lti_1p3_passport")]

    def setUp(self):
        super().setUp()
        self.executor = MigrationExecutor(connection)
        # Start from schema/state immediately before migration under test.
        self.executor.migrate(self.migrate_from)

        old_apps = self.executor.loader.project_state(self.migrate_from).apps
        LtiConfiguration = old_apps.get_model("lti_consumer", "LtiConfiguration")

        self.config_id = uuid.uuid4()
        self.location = "block-v1:org+course+run+type@lti+block@block"

        # Seed historical row using old app registry, not current model class.
        self.configuration = LtiConfiguration.objects.create(
            config_id=self.config_id,
            version="lti_1p3",
            config_store="CONFIG_ON_XBLOCK",
            location=self.location,
            lti_1p3_internal_private_key="db-private-key",
            lti_1p3_internal_private_key_id="db-kid",
            lti_1p3_internal_public_jwk='{"kty": "RSA"}',
            lti_1p3_client_id="db-client-id",
            lti_1p3_tool_public_key="db-tool-public-key",
            lti_1p3_tool_keyset_url="https://db.example/jwks.json",
        )

    def test_migration_creates_and_links_passport(self):
        """New-style block overrides tool key values from block fields."""
        class FakeBlock:
            """Dummy class for testing new-style block overrides"""
            config_type = "new"
            lti_1p3_tool_public_key = "xblock-tool-public-key"
            lti_1p3_tool_keyset_url = "https://xblock.example/jwks.json"

        fake_block = FakeBlock()
        values = {
            "lti_1p3_internal_private_key": "db-private-key",
            "lti_1p3_internal_private_key_id": "db-kid",
            "lti_1p3_internal_public_jwk": '{"kty": "RSA"}',
            "lti_1p3_client_id": "db-client-id",
            "lti_1p3_tool_public_key": "db-tool-public-key",
            "lti_1p3_tool_keyset_url": "https://db.example/jwks.json",
        }

        with mock.patch("lti_consumer.plugin.compat.load_enough_xblock", return_value=fake_block) as mock_load, \
                mock.patch("lti_consumer.plugin.compat.save_xblock") as mock_save_xblock, \
                mock.patch("lti_consumer.utils.model_to_dict", return_value=values):
            self.executor.loader.build_graph()
            self.executor.migrate(self.migrate_to)

        new_apps = self.executor.loader.project_state(self.migrate_to).apps
        LtiConfiguration = new_apps.get_model("lti_consumer", "LtiConfiguration")
        Lti1p3Passport = new_apps.get_model("lti_consumer", "Lti1p3Passport")

        configuration = LtiConfiguration.objects.get(pk=self.configuration.pk)
        passport = Lti1p3Passport.objects.get(passport_id=self.config_id)

        self.assertEqual(configuration.lti_1p3_passport_id, passport.id)
        self.assertEqual(passport.lti_1p3_internal_private_key, "db-private-key")
        self.assertEqual(passport.lti_1p3_internal_private_key_id, "db-kid")
        self.assertEqual(passport.lti_1p3_internal_public_jwk, '{"kty": "RSA"}')
        self.assertEqual(passport.lti_1p3_client_id, "db-client-id")
        self.assertEqual(passport.lti_1p3_tool_public_key, "xblock-tool-public-key")
        self.assertEqual(passport.lti_1p3_tool_keyset_url, "https://xblock.example/jwks.json")

        mock_load.assert_called_once()
        self.assertEqual(str(mock_load.call_args.args[0]), self.location)
        mock_save_xblock.assert_not_called()

    def test_migration_creates_passport_when_xblock_load_fails(self):
        """Missing location skips XBlock path but still creates passport from DB."""
        # No location means migration should not try loading or saving block.
        self.configuration.location = None
        self.configuration.save(update_fields=["location"])
        values = {
            "lti_1p3_internal_private_key": "db-private-key",
            "lti_1p3_internal_private_key_id": "db-kid",
            "lti_1p3_internal_public_jwk": '{"kty": "RSA"}',
            "lti_1p3_client_id": "db-client-id",
            "lti_1p3_tool_public_key": "db-tool-public-key",
            "lti_1p3_tool_keyset_url": "https://db.example/jwks.json",
        }

        with mock.patch(
            "lti_consumer.plugin.compat.load_enough_xblock",
            side_effect=Exception("boom"),
        ) as mock_load, mock.patch("lti_consumer.plugin.compat.save_xblock") as mock_save_xblock, \
                mock.patch("lti_consumer.utils.model_to_dict", return_value=values), \
                mock.patch("builtins.print") as mock_print:
            self.executor.loader.build_graph()
            self.executor.migrate(self.migrate_to)

        new_apps = self.executor.loader.project_state(self.migrate_to).apps
        LtiConfiguration = new_apps.get_model("lti_consumer", "LtiConfiguration")
        Lti1p3Passport = new_apps.get_model("lti_consumer", "Lti1p3Passport")

        configuration = LtiConfiguration.objects.get(pk=self.configuration.pk)
        passport = Lti1p3Passport.objects.get(passport_id=self.config_id)

        self.assertEqual(configuration.lti_1p3_passport_id, passport.id)
        self.assertEqual(passport.lti_1p3_internal_private_key, "db-private-key")
        self.assertEqual(passport.lti_1p3_internal_private_key_id, "db-kid")
        self.assertEqual(passport.lti_1p3_internal_public_jwk, '{"kty": "RSA"}')
        self.assertEqual(passport.lti_1p3_client_id, "db-client-id")
        self.assertEqual(passport.lti_1p3_tool_public_key, "db-tool-public-key")
        self.assertEqual(passport.lti_1p3_tool_keyset_url, "https://db.example/jwks.json")

        mock_load.assert_not_called()
        mock_save_xblock.assert_not_called()
        mock_print.assert_not_called()

    def test_migration_keeps_db_values_when_block_not_new(self):
        """Non-new block keeps DB tool key values even when block loads."""
        class FakeBlock:
            """Dummy class for testing new-style block overrides"""
            config_type = "legacy"
            lti_1p3_tool_public_key = "xblock-tool-public-key"
            lti_1p3_tool_keyset_url = "https://xblock.example/jwks.json"

        fake_block = FakeBlock()
        values = {
            "lti_1p3_internal_private_key": "db-private-key",
            "lti_1p3_internal_private_key_id": "db-kid",
            "lti_1p3_internal_public_jwk": '{"kty": "RSA"}',
            "lti_1p3_client_id": "db-client-id",
            "lti_1p3_tool_public_key": "db-tool-public-key",
            "lti_1p3_tool_keyset_url": "https://db.example/jwks.json",
        }

        with mock.patch("lti_consumer.plugin.compat.load_enough_xblock", return_value=fake_block) as mock_load, \
                mock.patch("lti_consumer.plugin.compat.save_xblock") as mock_save_xblock, \
                mock.patch("lti_consumer.utils.model_to_dict", return_value=values):
            self.executor.loader.build_graph()
            self.executor.migrate(self.migrate_to)

        new_apps = self.executor.loader.project_state(self.migrate_to).apps
        LtiConfiguration = new_apps.get_model("lti_consumer", "LtiConfiguration")
        Lti1p3Passport = new_apps.get_model("lti_consumer", "Lti1p3Passport")

        configuration = LtiConfiguration.objects.get(pk=self.configuration.pk)
        passport = Lti1p3Passport.objects.get(passport_id=self.config_id)

        self.assertEqual(configuration.lti_1p3_passport_id, passport.id)
        self.assertEqual(passport.lti_1p3_tool_public_key, "db-tool-public-key")
        self.assertEqual(passport.lti_1p3_tool_keyset_url, "https://db.example/jwks.json")

        self.assertEqual(str(mock_load.call_args.args[0]), self.location)
        mock_save_xblock.assert_not_called()


class Test0023SetPassportNameAndContextKey(TransactionTestCase):
    """Exercise data migration 0023 across success and edge-case paths."""

    reset_sequences = True

    migrate_from = [("lti_consumer", "0022_remove_lticonfiguration_lti_1p3_client_id_and_more")]
    migrate_to = [("lti_consumer", "0023_lti1p3passport_context_key_lti1p3passport_name_and_more")]

    def setUp(self):
        super().setUp()
        self.executor = MigrationExecutor(connection)
        # Start from schema/state immediately before migration under test.
        self.executor.migrate(self.migrate_from)

        old_apps = self.executor.loader.project_state(self.migrate_from).apps
        LtiConfiguration = old_apps.get_model("lti_consumer", "LtiConfiguration")
        Lti1p3Passport = old_apps.get_model("lti_consumer", "Lti1p3Passport")

        self.config_id = uuid.uuid4()
        self.location = "block-v1:org+course+run+type@lti+block@passport"

        # Seed historical rows using old app registry, not current model classes.
        self.passport = Lti1p3Passport.objects.create(
            passport_id=self.config_id,
            lti_1p3_internal_private_key="db-private-key",
            lti_1p3_internal_private_key_id="db-kid",
            lti_1p3_internal_public_jwk='{"kty": "RSA"}',
            lti_1p3_client_id="db-client-id",
            lti_1p3_tool_public_key="db-tool-public-key",
            lti_1p3_tool_keyset_url="https://db.example/jwks.json",
        )
        self.configuration = LtiConfiguration.objects.create(
            config_id=uuid.uuid4(),
            version="lti_1p3",
            config_store="CONFIG_ON_XBLOCK",
            location=self.location,
            lti_1p3_passport=self.passport,
        )

    def test_migration_sets_name_and_context_key_from_block(self):
        """Populate new passport fields from block when passport has no name yet."""

        class FakeBlock:
            """Dummy class for testing new-style block overrides"""
            display_name = "Unit 1 LTI"
            context_id = "course-v1:org+course+run"

        with mock.patch("lti_consumer.plugin.compat.load_enough_xblock", return_value=FakeBlock()) as mock_load:
            self.executor.loader.build_graph()
            self.executor.migrate(self.migrate_to)

        new_apps = self.executor.loader.project_state(self.migrate_to).apps
        Lti1p3Passport = new_apps.get_model("lti_consumer", "Lti1p3Passport")

        passport = Lti1p3Passport.objects.get(pk=self.passport.pk)

        self.assertEqual(passport.name, "Passport of Unit 1 LTI")
        self.assertEqual(passport.context_key, "course-v1:org+course+run")
        mock_load.assert_called_once()
        self.assertEqual(str(mock_load.call_args.args[0]), self.location)

    def test_migration_skips_xblock_path_when_location_missing(self):
        """Missing location skips block load and leaves new passport fields empty."""
        self.configuration.location = None
        self.configuration.save(update_fields=["location"])

        with mock.patch(
            "lti_consumer.plugin.compat.load_enough_xblock",
            side_effect=Exception("boom"),
        ) as mock_load, mock.patch("builtins.print") as mock_print:
            self.executor.loader.build_graph()
            self.executor.migrate(self.migrate_to)

        new_apps = self.executor.loader.project_state(self.migrate_to).apps
        Lti1p3Passport = new_apps.get_model("lti_consumer", "Lti1p3Passport")

        passport = Lti1p3Passport.objects.get(pk=self.passport.pk)

        self.assertIsNone(passport.name)
        self.assertIsNone(passport.context_key)
        mock_load.assert_not_called()
        mock_print.assert_not_called()

    def test_migration_keeps_existing_name_and_context_key(self):
        """Existing passport name prevents overwrite from block values."""

        class InitialBlock:
            display_name = "Initial title"
            context_id = "initial-context"

        with mock.patch("lti_consumer.plugin.compat.load_enough_xblock", return_value=InitialBlock()):
            self.executor.loader.build_graph()
            self.executor.migrate(self.migrate_to)

        new_apps = self.executor.loader.project_state(self.migrate_to).apps
        LtiConfiguration = new_apps.get_model("lti_consumer", "LtiConfiguration")
        Lti1p3Passport = new_apps.get_model("lti_consumer", "Lti1p3Passport")

        passport = Lti1p3Passport.objects.get(pk=self.passport.pk)
        passport.name = "Existing passport name"
        passport.context_key = "existing-context-key"
        passport.save(update_fields=["name", "context_key"])

        configuration = LtiConfiguration.objects.get(pk=self.configuration.pk)

        class FakeBlock:
            """Dummy class for testing new-style block overrides"""
            display_name = "Changed title"
            context_id = "changed-context"

        with mock.patch("lti_consumer.plugin.compat.load_enough_xblock", return_value=FakeBlock()) as mock_load:
            migration_module = importlib.import_module(
                "lti_consumer.migrations.0023_lti1p3passport_context_key_lti1p3passport_name_and_more"
            )
            migration_module.set_name_and_context_key(new_apps, None)

        passport.refresh_from_db()
        configuration.refresh_from_db()

        self.assertEqual(configuration.lti_1p3_passport_id, passport.id)
        self.assertEqual(passport.name, "Existing passport name")
        self.assertEqual(passport.context_key, "existing-context-key")
        self.assertEqual(str(mock_load.call_args.args[0]), self.location)
