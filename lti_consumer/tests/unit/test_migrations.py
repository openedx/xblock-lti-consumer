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
from django.db import connection, models
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import ProtectedError
from django.test import TransactionTestCase
from opaque_keys.edx.keys import CourseKey


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
    """Exercise the passport-table rename and the in-place conversion in 0024."""

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
        self.assertIsNone(passport.normalized_name)
        self.assertEqual(
            list(ReusableLtiConfiguration.objects.values_list("lti_1p3_client_id", flat=True)),
            ["shared-client-id", "shared-client-id"],
        )

    def test_conversion_fills_missing_metadata_and_keeps_the_placement_binding(self):
        """Only empty catalog fields are filled, from the lowest-PK placement."""
        new_apps = self.migrate()
        ReusableLtiConfiguration = new_apps.get_model("lti_consumer", "ReusableLtiConfiguration")
        LtiConfiguration = new_apps.get_model("lti_consumer", "LtiConfiguration")

        passport = ReusableLtiConfiguration.objects.get(pk=self.legacy_passport.pk)
        self.assertEqual(passport.context_type, "course")
        self.assertEqual(passport.context_key, "course-v1:Org+Course+Run")
        self.assertEqual(passport.version, "lti_1p3")
        self.assertEqual(passport.lti_1p3_launch_url, "https://tool.example/launch")
        self.assertEqual(passport.lti_1p3_oidc_url, "https://tool.example/oidc")
        self.assertEqual(passport.lti_1p3_redirect_uris, ["https://tool.example/redirect"])
        self.assertEqual(passport.lti_advantage_ags_mode, "programmatic")

        placement = LtiConfiguration.objects.get(pk=self.placement.pk)
        self.assertEqual(placement.lti_1p3_passport_id, passport.pk)
        self.assertEqual(placement.location, self.placement.location)

        # A row that never had signing material gets none during the conversion.
        bare = ReusableLtiConfiguration.objects.get(pk=self.bare_passport.pk)
        self.assertEqual(bare.lti_1p3_internal_private_key, "")
        self.assertEqual(bare.lti_1p3_internal_public_jwk, "")
        self.assertEqual(bare.lti_1p3_internal_private_key_id, "")

    def test_orphan_passport_keeps_an_unassigned_context(self):
        """A legacy context that is not a course key is preserved but leaves no context."""
        Lti1p3Passport = self.old_apps.get_model("lti_consumer", "Lti1p3Passport")
        orphan = Lti1p3Passport.objects.create(
            lti_1p3_client_id="orphan-client",
            context_key="not-a-course-key",
        )

        new_apps = self.migrate()
        ReusableLtiConfiguration = new_apps.get_model("lti_consumer", "ReusableLtiConfiguration")

        row = ReusableLtiConfiguration.objects.get(pk=orphan.pk)
        self.assertIsNone(row.context_type)
        self.assertEqual(row.context_key, "not-a-course-key")

    def test_conversion_is_idempotent_and_reports_incomplete_rows(self):
        """A second run changes nothing and the incomplete rows stay visible."""
        new_apps = self.migrate()
        ReusableLtiConfiguration = new_apps.get_model("lti_consumer", "ReusableLtiConfiguration")
        migration_module = importlib.import_module("lti_consumer.migrations.0024_reusable_lti_configuration")

        before = list(ReusableLtiConfiguration.objects.order_by("pk").values())
        with mock.patch.object(migration_module, "log") as mock_log:
            migration_module.convert_passports(new_apps, None)
        after = list(ReusableLtiConfiguration.objects.order_by("pk").values())

        self.assertEqual(before, after)
        warnings = [call.args[0] for call in mock_log.warning.call_args_list]
        self.assertTrue(any("incomplete configurations" in message for message in warnings))
        self.assertTrue(
            any(str(self.passport_id) in str(call.args[1]) for call in mock_log.warning.call_args_list),
        )

    def test_conversion_seeds_and_preserves_the_legacy_deployment_id(self):
        """Converted 1.3 rows keep the historical deployment "1"; an explicit value survives."""
        self.make_placement(
            self.bare_passport, "CONFIG_ON_DB",
            "block-v1:Org+Course+Run+type@lti_consumer+block@bare-deployment",
            lti_1p3_launch_url="https://tool.example/launch",
            lti_1p3_oidc_url="https://tool.example/oidc",
        )
        migration_module = importlib.import_module("lti_consumer.migrations.0024_reusable_lti_configuration")

        new_apps = self.migrate()
        ReusableLtiConfiguration = new_apps.get_model("lti_consumer", "ReusableLtiConfiguration")

        self.assertEqual(
            ReusableLtiConfiguration.objects.get(pk=self.legacy_passport.pk).lti_1p3_deployment_id, "1",
        )
        seeded = ReusableLtiConfiguration.objects.get(pk=self.bare_passport.pk)
        self.assertEqual(seeded.lti_1p3_deployment_id, "1")

        seeded.lti_1p3_deployment_id = "tool-deployment"
        seeded.save(update_fields=["lti_1p3_deployment_id"])
        migration_module.convert_passports(new_apps, None)
        seeded.refresh_from_db()
        self.assertEqual(seeded.lti_1p3_deployment_id, "tool-deployment")

    def test_conversion_seeds_lti_1p1_credentials_from_the_same_placement(self):
        """A 1.1 block supplies the course lti_passports key/secret, for DB placements too."""
        Lti1p3Passport = self.old_apps.get_model("lti_consumer", "Lti1p3Passport")
        xblock_passport = Lti1p3Passport.objects.create(lti_1p3_client_id="one-one-xblock")
        db_passport = Lti1p3Passport.objects.create(lti_1p3_client_id="one-one-db")
        self.make_placement(
            xblock_passport, "CONFIG_ON_XBLOCK",
            "block-v1:Org+Course+Run+type@lti_consumer+block@one-one-xblock", version="lti_1p1",
        )
        self.make_placement(
            db_passport, "CONFIG_ON_DB",
            "block-v1:Org+Course+Run+type@lti_consumer+block@one-one-db",
            version="lti_1p1", lti_1p1_launch_url="https://tool.example/db-launch",
        )

        class FakeBlock:
            """A readable LTI 1.1 block resolving its credentials from the course."""

            lti_version = "lti_1p1"
            launch_url = "https://tool.example/xblock-launch"
            lti_provider_key_secret = ("course-key", "course-secret")

        with mock.patch("lti_consumer.plugin.compat.load_enough_xblock", return_value=FakeBlock()):
            new_apps = self.migrate()

        ReusableLtiConfiguration = new_apps.get_model("lti_consumer", "ReusableLtiConfiguration")
        xblock_row = ReusableLtiConfiguration.objects.get(pk=xblock_passport.pk)
        self.assertEqual(xblock_row.version, "lti_1p1")
        self.assertEqual(xblock_row.lti_1p1_launch_url, "https://tool.example/xblock-launch")
        self.assertEqual(xblock_row.lti_1p1_client_key, "course-key")
        self.assertEqual(xblock_row.lti_1p1_client_secret, "course-secret")

        db_row = ReusableLtiConfiguration.objects.get(pk=db_passport.pk)
        self.assertEqual(db_row.lti_1p1_launch_url, "https://tool.example/db-launch")
        self.assertEqual(db_row.lti_1p1_client_key, "course-key")
        self.assertEqual(db_row.lti_1p1_client_secret, "course-secret")

    def test_lti_1p1_credentials_skip_an_unreadable_placement(self):
        """An unreadable first candidate is reported, and the next eligible placement supplies the bundle."""
        Lti1p3Passport = self.old_apps.get_model("lti_consumer", "Lti1p3Passport")
        passport = Lti1p3Passport.objects.create(lti_1p3_client_id="one-one-fallback")
        self.make_placement(
            passport, "CONFIG_ON_XBLOCK",
            "block-v1:Org+Course+Run+type@lti_consumer+block@broken", version="lti_1p1",
        )
        self.make_placement(
            passport, "CONFIG_ON_XBLOCK",
            "block-v1:Org+Course+Run+type@lti_consumer+block@working", version="lti_1p1",
        )

        class FakeBlock:
            """The readable second candidate."""

            lti_version = "lti_1p1"
            launch_url = "https://tool.example/next-launch"
            lti_provider_key_secret = ("next-key", "next-secret")

        def load(location):
            if str(location).endswith("@broken"):
                raise RuntimeError("modulestore unavailable")
            return FakeBlock()

        migration_module = importlib.import_module("lti_consumer.migrations.0024_reusable_lti_configuration")
        with mock.patch("lti_consumer.plugin.compat.load_enough_xblock", side_effect=load), \
                mock.patch.object(migration_module, "log") as mock_log:
            new_apps = self.migrate()

        ReusableLtiConfiguration = new_apps.get_model("lti_consumer", "ReusableLtiConfiguration")
        row = ReusableLtiConfiguration.objects.get(pk=passport.pk)
        self.assertEqual(row.lti_1p1_launch_url, "https://tool.example/next-launch")
        self.assertEqual(row.lti_1p1_client_key, "next-key")
        self.assertEqual(row.lti_1p1_client_secret, "next-secret")
        self.assertTrue(
            any("@broken" in str(call.args[1]) for call in mock_log.warning.call_args_list),
        )

    def test_external_placement_never_supplies_a_bundle(self):
        """External configurations stay dynamic references and are never converted."""
        Lti1p3Passport = self.old_apps.get_model("lti_consumer", "Lti1p3Passport")
        passport = Lti1p3Passport.objects.create(lti_1p3_client_id="external-only")
        self.make_placement(
            passport, "CONFIG_EXTERNAL",
            "block-v1:Org+Course+Run+type@lti_consumer+block@external",
            external_id="tool:slug",
        )

        with mock.patch("lti_consumer.plugin.compat.load_enough_xblock") as mock_load:
            new_apps = self.migrate()

        ReusableLtiConfiguration = new_apps.get_model("lti_consumer", "ReusableLtiConfiguration")
        row = ReusableLtiConfiguration.objects.get(pk=passport.pk)
        self.assertIsNone(row.version)
        self.assertIsNone(row.lti_1p1_launch_url)
        self.assertIsNone(row.lti_1p3_launch_url)
        self.assertIsNone(row.lti_1p3_deployment_id)
        mock_load.assert_not_called()

    def make_placement(self, passport, config_store, location, **kwargs):
        """Create a placement in the 0023 schema, bypassing the runtime model."""
        LtiConfiguration = self.old_apps.get_model("lti_consumer", "LtiConfiguration")
        values = {
            "config_id": uuid.uuid4(),
            "version": "lti_1p3",
            "config_store": config_store,
            "location": location,
            "lti_1p3_passport": passport,
        }
        values.update(kwargs)
        return LtiConfiguration.objects.create(**values)

    def test_xblock_source_seeds_defaults_and_infers_keyset_mode(self):
        """A readable block supplies the bundle; the mode follows the passport keys, not the block default."""
        Lti1p3Passport = self.old_apps.get_model("lti_consumer", "Lti1p3Passport")
        passport = Lti1p3Passport.objects.create(
            lti_1p3_client_id="keyset-client",
            lti_1p3_tool_keyset_url="https://tool.example/jwks.json",
        )
        self.make_placement(
            passport, "CONFIG_ON_XBLOCK", "block-v1:Org+Course+Run+type@lti_consumer+block@xblock",
        )

        class FakeBlock:
            """Block settings a legacy XBLOCK placement contributes."""

            lti_version = "lti_1p3"
            lti_1p3_launch_url = "https://tool.example/launch"
            lti_1p3_oidc_url = "https://tool.example/oidc"
            lti_1p3_redirect_uris = ["https://tool.example/redirect"]
            lti_1p3_tool_key_mode = "public_key"  # the block default must not win
            lti_advantage_deep_linking_enabled = True
            lti_advantage_deep_linking_launch_url = "https://tool.example/deep-linking"
            lti_advantage_ags_mode = "programmatic"
            lti_1p3_enable_nrps = True
            display_name = "Block title"
            has_score = True
            weight = 5.0
            accept_grades_past_due = False
            launch_target = "modal"
            inline_height = 500
            modal_height = 70
            modal_width = 60
            button_text = "Open"
            custom_parameters = ["a=b"]

        with mock.patch(
            "lti_consumer.plugin.compat.load_enough_xblock", return_value=FakeBlock(),
        ) as mock_load:
            new_apps = self.migrate()

        ReusableLtiConfiguration = new_apps.get_model("lti_consumer", "ReusableLtiConfiguration")
        row = ReusableLtiConfiguration.objects.get(pk=passport.pk)
        self.assertEqual(row.version, "lti_1p3")
        self.assertEqual(row.lti_1p3_launch_url, "https://tool.example/launch")
        self.assertEqual(row.lti_1p3_oidc_url, "https://tool.example/oidc")
        self.assertEqual(row.lti_1p3_redirect_uris, ["https://tool.example/redirect"])
        self.assertTrue(row.lti_advantage_deep_linking_enabled)
        self.assertTrue(row.lti_advantage_enable_nrps)
        self.assertEqual(row.lti_advantage_ags_mode, "programmatic")
        self.assertEqual(row.display_name, "Block title")
        self.assertTrue(row.enable_grading)
        self.assertEqual(row.grade_weight, 5.0)
        self.assertFalse(row.accept_grades_after_due_date)
        self.assertEqual(row.open_tool_in, "modal")
        self.assertEqual(row.inline_height, 500)
        self.assertEqual(row.modal_height, 70)
        self.assertEqual(row.modal_width, 60)
        self.assertEqual(row.launch_button_text, "Open")
        self.assertEqual(row.custom_parameters, ["a=b"])
        # Keyset-only passport material decides the mode; the block default does not.
        self.assertEqual(row.lti_1p3_tool_key_mode, "keyset_url")
        self.assertEqual(row.lti_1p3_tool_public_key, "")
        self.assertEqual(row.lti_1p3_tool_keyset_url, "https://tool.example/jwks.json")
        mock_load.assert_called()

    def test_ambiguous_or_missing_tool_key_material_leaves_mode_unset(self):
        """Neither an ambiguous nor an empty key pair invents a mode, whatever the block claims."""
        Lti1p3Passport = self.old_apps.get_model("lti_consumer", "Lti1p3Passport")
        ambiguous = Lti1p3Passport.objects.create(
            lti_1p3_client_id="ambiguous-client",
            lti_1p3_tool_public_key="public-key",
            lti_1p3_tool_keyset_url="https://tool.example/jwks.json",
        )
        keyless = Lti1p3Passport.objects.create(lti_1p3_client_id="keyless-client")
        self.make_placement(
            ambiguous, "CONFIG_ON_XBLOCK", "block-v1:Org+Course+Run+type@lti_consumer+block@ambiguous",
        )
        self.make_placement(
            keyless, "CONFIG_ON_XBLOCK", "block-v1:Org+Course+Run+type@lti_consumer+block@keyless",
        )

        class FakeBlock:
            """A block that claims a mode its passport material does not support."""

            lti_version = "lti_1p3"
            lti_1p3_tool_key_mode = "keyset_url"

        with mock.patch("lti_consumer.plugin.compat.load_enough_xblock", return_value=FakeBlock()):
            new_apps = self.migrate()

        ReusableLtiConfiguration = new_apps.get_model("lti_consumer", "ReusableLtiConfiguration")
        self.assertIsNone(ReusableLtiConfiguration.objects.get(pk=ambiguous.pk).lti_1p3_tool_key_mode)
        self.assertIsNone(ReusableLtiConfiguration.objects.get(pk=keyless.pk).lti_1p3_tool_key_mode)

    def test_unreadable_block_is_reported_and_the_row_still_migrates(self):
        """An unreadable XBlock is reported by location, and its configuration still converts."""
        Lti1p3Passport = self.old_apps.get_model("lti_consumer", "Lti1p3Passport")
        passport = Lti1p3Passport.objects.create(lti_1p3_client_id="unreadable-client")
        location = "block-v1:Org+Course+Run+type@lti_consumer+block@unreadable"
        self.make_placement(passport, "CONFIG_ON_XBLOCK", location)
        migration_module = importlib.import_module("lti_consumer.migrations.0024_reusable_lti_configuration")

        with mock.patch(
            "lti_consumer.plugin.compat.load_enough_xblock", side_effect=Exception("boom"),
        ), mock.patch.object(migration_module, "log") as mock_log:
            new_apps = self.migrate()

        ReusableLtiConfiguration = new_apps.get_model("lti_consumer", "ReusableLtiConfiguration")
        row = ReusableLtiConfiguration.objects.get(pk=passport.pk)
        self.assertEqual(row.lti_1p3_client_id, "unreadable-client")
        self.assertIsNone(row.lti_1p3_launch_url)
        self.assertEqual(row.context_type, "course")
        self.assertTrue(
            any("unreadable" in str(call.args[0]).lower() and location in str(call.args)
                for call in mock_log.warning.call_args_list),
        )

    def test_incomplete_reporting_uses_version_specific_requirements(self):
        """Reporting lists what each version needs; fields the source supplied are not reported."""
        Lti1p3Passport = self.old_apps.get_model("lti_consumer", "Lti1p3Passport")
        lti_11 = Lti1p3Passport.objects.create(
            name="1.1 tool", context_key="course-v1:Org+Course+Run", lti_1p3_client_id="lti11-client",
        )
        self.make_placement(
            lti_11, "CONFIG_ON_DB", "block-v1:Org+Course+Run+type@lti_consumer+block@lti11",
            version="lti_1p1", lti_1p1_launch_url="https://tool.example/launch-11",
        )
        # A 1.3 registration with no connection data at all.
        sparse = Lti1p3Passport.objects.create(name="Sparse 1.3 tool", lti_1p3_client_id="sparse-client")
        self.make_placement(
            sparse, "CONFIG_ON_DB", "block-v1:Org+Course+Run+type@lti_consumer+block@sparse",
        )
        migration_module = importlib.import_module("lti_consumer.migrations.0024_reusable_lti_configuration")

        class CredentialFreeBlock:
            """A readable LTI 1.1 block whose course passport entry is empty."""

            lti_version = "lti_1p1"
            launch_url = "https://tool.example/launch-11"
            lti_provider_key_secret = ("", "")

        with mock.patch(
            "lti_consumer.plugin.compat.load_enough_xblock", return_value=CredentialFreeBlock(),
        ):
            new_apps = self.migrate()
        ReusableLtiConfiguration = new_apps.get_model("lti_consumer", "ReusableLtiConfiguration")

        self.assertEqual(ReusableLtiConfiguration.objects.get(pk=lti_11.pk).version, "lti_1p1")
        with mock.patch.object(migration_module, "log") as mock_log:
            migration_module.convert_passports(new_apps, None)
        reported = [str(entry) for entry in mock_log.warning.call_args_list[-1].args[1]]

        def report_for(passport_id):
            return next(entry for entry in reported if str(passport_id) in entry)

        lti_11_report = report_for(lti_11.passport_id)
        self.assertIn("lti_1p1_client_key", lti_11_report)
        self.assertIn("lti_1p1_client_secret", lti_11_report)
        self.assertNotIn("lti_1p1_launch_url", lti_11_report)
        self.assertNotIn("lti_1p3_", lti_11_report)

        sparse_report = report_for(sparse.passport_id)
        for field in (
            "lti_1p3_launch_url", "lti_1p3_oidc_url", "lti_1p3_redirect_uris", "lti_1p3_tool_key",
        ):
            self.assertIn(field, sparse_report)
        self.assertNotIn("lti_1p3_client_id", sparse_report)
        # Legacy launches claimed deployment "1", so conversion seeds it instead of reporting it.
        self.assertNotIn("lti_1p3_deployment_id", sparse_report)

        complete_report = report_for(self.passport_id)
        self.assertNotIn("lti_1p3_launch_url", complete_report)
        self.assertIn("lti_1p3_tool_key_mode", complete_report)  # ambiguous key material

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

    def test_ccx_stored_context_uses_the_parent_course(self):
        """A stored CCX context key becomes the course it copies."""
        Lti1p3Passport = self.old_apps.get_model("lti_consumer", "Lti1p3Passport")
        passport = Lti1p3Passport.objects.create(
            lti_1p3_client_id="ccx-stored", context_key="ccx-v1:Org+Course+Run+ccx@1",
        )
        new_apps = self.migrate()
        ReusableLtiConfiguration = new_apps.get_model("lti_consumer", "ReusableLtiConfiguration")

        row = ReusableLtiConfiguration.objects.get(pk=passport.pk)
        self.assertEqual(row.context_type, "course")
        self.assertEqual(row.context_key, "course-v1:Org+Course+Run")

    def test_ccx_placement_location_uses_the_parent_course(self):
        """A CCX placement location falls back to the course it copies."""
        migration_module = importlib.import_module("lti_consumer.migrations.0024_reusable_lti_configuration")
        ccx_course = CourseKey.from_string("ccx-v1:Org+Course+Run+ccx@1")
        placement = mock.Mock(
            location=ccx_course.make_usage_key("lti_consumer", "one"),
            config_store="CONFIG_ON_DB",
        )
        self.assertEqual(
            migration_module._placement_context([placement]), ("course", "course-v1:Org+Course+Run"),
        )


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
