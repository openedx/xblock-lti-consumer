"""
Tests for custom migrations scripts
"""
import importlib
import uuid
from unittest import mock

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import FieldDoesNotExist
from django.core.management import call_command
from django.db import connection, migrations, models
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import ProtectedError
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

    def test_backwards_copies_passport_values_back_to_configuration(self):
        """Reverse migration restores passport-backed values onto the configuration."""
        values = {
            "lti_1p3_internal_private_key": "db-private-key",
            "lti_1p3_internal_private_key_id": "db-kid",
            "lti_1p3_internal_public_jwk": '{"kty": "RSA"}',
            "lti_1p3_client_id": "db-client-id",
            "lti_1p3_tool_public_key": "db-tool-public-key",
            "lti_1p3_tool_keyset_url": "https://db.example/jwks.json",
        }

        with mock.patch("lti_consumer.plugin.compat.load_enough_xblock", side_effect=Exception("boom")), \
                mock.patch("lti_consumer.utils.model_to_dict", return_value=values):
            self.executor.loader.build_graph()
            self.executor.migrate(self.migrate_to)

        new_apps = self.executor.loader.project_state(self.migrate_to).apps
        LtiConfiguration = new_apps.get_model("lti_consumer", "LtiConfiguration")
        Lti1p3Passport = new_apps.get_model("lti_consumer", "Lti1p3Passport")

        configuration = LtiConfiguration.objects.get(pk=self.configuration.pk)
        passport = Lti1p3Passport.objects.get(passport_id=self.config_id)

        new_config_id = uuid.uuid4()
        configuration.config_id = new_config_id
        configuration.lti_1p3_internal_private_key = ""
        configuration.lti_1p3_internal_private_key_id = ""
        configuration.lti_1p3_internal_public_jwk = ""
        configuration.lti_1p3_client_id = ""
        configuration.lti_1p3_tool_public_key = ""
        configuration.lti_1p3_tool_keyset_url = ""
        configuration.lti_config = {"existing": "value"}
        configuration.save()

        migration_module = importlib.import_module("lti_consumer.migrations.0021_create_lti_1p3_passport")
        migration_module.backwards(new_apps, None)

        configuration.refresh_from_db()

        self.assertEqual(configuration.lti_1p3_internal_private_key, passport.lti_1p3_internal_private_key)
        self.assertEqual(configuration.lti_1p3_internal_private_key_id, passport.lti_1p3_internal_private_key_id)
        self.assertEqual(configuration.lti_1p3_internal_public_jwk, passport.lti_1p3_internal_public_jwk)
        self.assertEqual(configuration.lti_1p3_client_id, passport.lti_1p3_client_id)
        self.assertEqual(configuration.config_id, passport.passport_id)
        self.assertNotEqual(configuration.config_id, new_config_id)
        self.assertEqual(configuration.lti_1p3_tool_public_key, passport.lti_1p3_tool_public_key)
        self.assertEqual(configuration.lti_1p3_tool_keyset_url, passport.lti_1p3_tool_keyset_url)
        self.assertEqual(configuration.lti_config, {"existing": "value"})


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


class Test0024PassportExtension(TransactionTestCase):
    """Exercise the structural rename and column additions in 0024."""

    reset_sequences = True

    migrate_from = [("lti_consumer", "0023_lti1p3passport_context_key_lti1p3passport_name_and_more")]
    migrate_to = [("lti_consumer", "0024_reusable_lti_configuration")]

    def setUp(self):
        super().setUp()
        self.executor = MigrationExecutor(connection)
        # Start from schema/state immediately before migration under test.
        self.executor.migrate(self.migrate_from)

        self.old_apps = self.executor.loader.project_state(self.migrate_from).apps
        LtiConfiguration = self.old_apps.get_model("lti_consumer", "LtiConfiguration")
        Lti1p3Passport = self.old_apps.get_model("lti_consumer", "Lti1p3Passport")

        self.passport_id = uuid.uuid4()
        self.legacy_passport = Lti1p3Passport.objects.create(
            passport_id=self.passport_id,
            name=None,
            context_key="course-v1:Org+Course+Run",
            lti_1p3_internal_private_key="private-key",
            lti_1p3_internal_private_key_id="kid",
            lti_1p3_internal_public_jwk='{"kty": "RSA"}',
            lti_1p3_client_id="shared-client-id",
            lti_1p3_tool_public_key="tool-public-key",
            lti_1p3_tool_keyset_url="https://tool.example/jwks.json",
        )
        # Approved legacy state: a duplicate Client ID and a row with no key material.
        self.bare_passport = Lti1p3Passport.objects.create(lti_1p3_client_id="shared-client-id")
        self.placement = LtiConfiguration.objects.create(
            config_id=uuid.uuid4(),
            version="lti_1p3",
            config_store="CONFIG_ON_DB",
            location="block-v1:Org+Course+Run+type@lti_consumer+block@one",
            lti_1p3_passport=self.legacy_passport,
            lti_1p3_launch_url="https://tool.example/launch",
            lti_1p3_oidc_url="https://tool.example/oidc",
            lti_1p3_redirect_uris=["https://tool.example/redirect"],
            lti_advantage_ags_mode="programmatic",
        )

    def migrate(self):
        """Apply 0024 and return the resulting application state."""
        self.executor.loader.build_graph()
        self.executor.migrate(self.migrate_to)
        return self.executor.loader.project_state(self.migrate_to).apps

    def test_rename_keeps_one_table_and_preserves_passport_rows(self):
        """The passport table is renamed, never recreated, and every value survives."""
        new_apps = self.migrate()
        ReusableLtiConfiguration = new_apps.get_model("lti_consumer", "ReusableLtiConfiguration")

        with self.assertRaises(LookupError):
            new_apps.get_model("lti_consumer", "Lti1p3Passport")

        tables = connection.introspection.table_names()
        self.assertIn("lti_consumer_reusablelticonfiguration", tables)
        self.assertNotIn("lti_consumer_lti1p3passport", tables)

        self.assertEqual(ReusableLtiConfiguration.objects.count(), 2)
        passport = ReusableLtiConfiguration.objects.get(pk=self.legacy_passport.pk)
        self.assertEqual(passport.passport_id, self.passport_id)
        self.assertEqual(passport.lti_1p3_client_id, "shared-client-id")
        self.assertEqual(passport.lti_1p3_internal_private_key, "private-key")
        self.assertEqual(passport.lti_1p3_internal_private_key_id, "kid")
        self.assertEqual(passport.lti_1p3_internal_public_jwk, '{"kty": "RSA"}')
        self.assertEqual(passport.lti_1p3_tool_public_key, "tool-public-key")
        self.assertEqual(passport.lti_1p3_tool_keyset_url, "https://tool.example/jwks.json")
        self.assertIsNone(passport.name)
        self.assertEqual(
            list(ReusableLtiConfiguration.objects.values_list("lti_1p3_client_id", flat=True)),
            ["shared-client-id", "shared-client-id"],
        )

    def test_no_conversion_and_no_block_or_modulestore_read(self):
        """0024 reads no block and leaves legacy configuration and placement values untouched."""
        migration_module = importlib.import_module("lti_consumer.migrations.0024_reusable_lti_configuration")
        self.assertFalse([
            operation for operation in migration_module.Migration.operations
            if isinstance(operation, migrations.RunPython)
        ])

        # Legacy rows can hold a malformed context and an unnormalized name.
        self.bare_passport.context_key = "not-a-course-key"
        self.bare_passport.name = "  Legacy NAME  "
        self.bare_passport.save(update_fields=["context_key", "name"])

        with mock.patch(
            "lti_consumer.plugin.compat.load_enough_xblock", side_effect=AssertionError("block read"),
        ) as mock_load:
            new_apps = self.migrate()
        mock_load.assert_not_called()

        ReusableLtiConfiguration = new_apps.get_model("lti_consumer", "ReusableLtiConfiguration")
        LtiConfiguration = new_apps.get_model("lti_consumer", "LtiConfiguration")

        row = ReusableLtiConfiguration.objects.get(pk=self.legacy_passport.pk)
        # The legacy context stays a raw string instead of being parsed into catalog metadata.
        self.assertEqual(row.context_key, "course-v1:Org+Course+Run")
        self.assertIsNone(row.context_type)
        self.assertIsNone(row.version)
        # The placement's connection settings are not copied onto the configuration.
        self.assertIsNone(row.lti_1p3_launch_url)
        self.assertIsNone(row.lti_1p3_oidc_url)
        self.assertEqual(row.lti_1p3_redirect_uris, [])
        self.assertEqual(row.lti_advantage_ags_mode, "declarative")
        self.assertFalse(row.lti_advantage_deep_linking_enabled)
        self.assertIsNone(row.lti_1p3_deployment_id)
        self.assertIsNone(row.lti_1p3_tool_key_mode)
        self.assertEqual(row.description, "")

        # A malformed context and an unnormalized name are neither parsed nor rewritten.
        bare = ReusableLtiConfiguration.objects.get(pk=self.bare_passport.pk)
        self.assertEqual(bare.context_key, "not-a-course-key")
        self.assertIsNone(bare.context_type)
        self.assertEqual(bare.name, "  Legacy NAME  ")
        # A row without signing material gets none.
        self.assertEqual(bare.lti_1p3_internal_private_key, "")
        self.assertEqual(bare.lti_1p3_internal_public_jwk, "")
        self.assertEqual(bare.lti_1p3_internal_private_key_id, "")

        placement = LtiConfiguration.objects.get(pk=self.placement.pk)
        self.assertEqual(placement.lti_1p3_passport_id, self.legacy_passport.pk)
        self.assertEqual(placement.location, self.placement.location)
        self.assertEqual(placement.config_store, "CONFIG_ON_DB")
        self.assertEqual(placement.lti_1p3_launch_url, "https://tool.example/launch")
        self.assertEqual(placement.lti_1p3_oidc_url, "https://tool.example/oidc")
        self.assertEqual(placement.lti_1p3_redirect_uris, ["https://tool.example/redirect"])
        self.assertEqual(placement.lti_advantage_ags_mode, "programmatic")

    def test_placement_binding_protects_the_configuration_row(self):
        """0024 switches the placement FK from SET_NULL to PROTECT."""
        new_apps = self.migrate()
        ReusableLtiConfiguration = new_apps.get_model("lti_consumer", "ReusableLtiConfiguration")
        LtiConfiguration = new_apps.get_model("lti_consumer", "LtiConfiguration")

        self.assertIs(
            LtiConfiguration._meta.get_field("lti_1p3_passport").remote_field.on_delete, models.PROTECT,
        )
        configuration = ReusableLtiConfiguration.objects.get(pk=self.legacy_passport.pk)
        with self.assertRaises(ProtectedError):
            configuration.delete()
        self.assertTrue(ReusableLtiConfiguration.objects.filter(pk=configuration.pk).exists())

        # Removing the last placement releases the configuration.
        LtiConfiguration.objects.get(pk=self.placement.pk).delete()
        configuration.delete()
        self.assertFalse(ReusableLtiConfiguration.objects.filter(pk=configuration.pk).exists())

    def test_reverse_migration_restores_the_passport_table(self):
        """Reversal renames the table back and keeps every passport value and binding."""
        new_apps = self.migrate()
        ReusableLtiConfiguration = new_apps.get_model("lti_consumer", "ReusableLtiConfiguration")
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 2)

        self.executor.loader.build_graph()
        self.executor.migrate(self.migrate_from)
        old_apps = self.executor.loader.project_state(self.migrate_from).apps
        Lti1p3Passport = old_apps.get_model("lti_consumer", "Lti1p3Passport")
        LtiConfiguration = old_apps.get_model("lti_consumer", "LtiConfiguration")

        tables = connection.introspection.table_names()
        self.assertIn("lti_consumer_lti1p3passport", tables)
        self.assertNotIn("lti_consumer_reusablelticonfiguration", tables)

        passport = Lti1p3Passport.objects.get(pk=self.legacy_passport.pk)
        self.assertEqual(passport.passport_id, self.passport_id)
        self.assertEqual(passport.lti_1p3_internal_private_key, "private-key")
        self.assertEqual(passport.lti_1p3_tool_public_key, "tool-public-key")
        self.assertIsNone(passport.name)
        with self.assertRaises(FieldDoesNotExist):
            Lti1p3Passport._meta.get_field("version")
        self.assertEqual(
            LtiConfiguration.objects.get(pk=self.placement.pk).lti_1p3_passport_id, passport.pk,
        )
        # Leave the suite on the latest schema.
        self.migrate()


class Test0024ContentTypePreservation(TransactionTestCase):
    """Django's pre_migrate hook must rename the content type in place, keeping its id and grants."""

    migrate_from = [("lti_consumer", "0023_lti1p3passport_context_key_lti1p3passport_name_and_more")]
    migrate_to = [("lti_consumer", "0024_reusable_lti_configuration")]

    def test_rename_preserves_the_content_type_id_and_grants(self):
        """A migrated deployment keeps one content-type row and the permissions attached to it."""
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)

        # Simulate a deployed database: one passport content type with a grant.
        ContentType.objects.filter(app_label="lti_consumer").delete()
        content_type = ContentType.objects.create(app_label="lti_consumer", model="lti1p3passport")
        permission = Permission.objects.create(
            content_type=content_type,
            codename="change_lti1p3passport",
            name="Can change LTI passport",
        )
        group = Group.objects.create(name="passport-admins")
        group.permissions.add(permission)
        content_type_id = content_type.pk

        # The real management command emits pre_migrate, which injects RenameContentType.
        call_command(
            "migrate", "lti_consumer", self.migrate_to[0][1], verbosity=0, interactive=False,
        )

        renamed = ContentType.objects.get(pk=content_type_id)
        self.assertEqual((renamed.app_label, renamed.model), ("lti_consumer", "reusablelticonfiguration"))
        self.assertEqual(
            ContentType.objects.filter(app_label="lti_consumer", model="reusablelticonfiguration").count(), 1,
        )
        self.assertEqual(Permission.objects.get(pk=permission.pk).content_type_id, content_type_id)
        self.assertTrue(Group.objects.get(pk=group.pk).permissions.filter(pk=permission.pk).exists())
