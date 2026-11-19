"""
Tests for custom migrations scripts
"""
import contextlib
import importlib
import io
import uuid
from unittest import mock

from django.apps import apps as django_apps
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.db import connection, models
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


BASE_MIGRATION = ("lti_consumer", "0023_lti1p3passport_context_key_lti1p3passport_name_and_more")
SCHEMA_MIGRATION = ("lti_consumer", "0024_create_reusable_lti_configuration")
COPY_MIGRATION = ("lti_consumer", "0025_copy_lti1p3_passports")

# The nine values a passport contributes to its copy; the new row owns its id and timestamps.
PASSPORT_FIELDS = (
    "passport_id",
    "name",
    "context_key",
    "lti_1p3_internal_private_key",
    "lti_1p3_internal_private_key_id",
    "lti_1p3_internal_public_jwk",
    "lti_1p3_client_id",
    "lti_1p3_tool_public_key",
    "lti_1p3_tool_keyset_url",
)

# Compare only fields copied unchanged; `context_key` is inferred for new copies.
PRESERVED_FIELDS = tuple(field for field in PASSPORT_FIELDS if field != "context_key")

CONFIG_EXTERNAL = "CONFIG_EXTERNAL"


class RestoreLatestMigrationMixin:
    """Leave the test database on the newest migration, even when fixture setup fails."""

    def setUp(self):
        # Registered before any migration so a failing fixture cannot strand the database.
        self.addCleanup(self.restore_latest_migration)
        super().setUp()

    def restore_latest_migration(self):
        """Migrate forward to the copy migration; a conflict fixture repairs only itself."""
        MigrationExecutor(connection).migrate([COPY_MIGRATION])


class Test0021CreateLti1p3Passport(RestoreLatestMigrationMixin, TransactionTestCase):
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


class Test0023SetPassportNameAndContextKey(RestoreLatestMigrationMixin, TransactionTestCase):
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


class PassportCopyHarness(RestoreLatestMigrationMixin, TransactionTestCase):
    """Migrate to 0023 and seed fixtures with the historical models."""

    reset_sequences = True

    def setUp(self):
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.executor.migrate([BASE_MIGRATION])
        self.old_apps = self.executor.loader.project_state([BASE_MIGRATION]).apps
        self.Passport = self.old_apps.get_model("lti_consumer", "Lti1p3Passport")
        self.Placement = self.old_apps.get_model("lti_consumer", "LtiConfiguration")
        self.seed()

    def seed(self):
        """Create one passport per fixture class, shared by the placements that need them."""
        self.plain = self.passport()
        self.shared = self.passport(name="Shared", lti_1p3_client_id="shared-client")
        self.orphan = self.passport(
            name=None,
            context_key=None,
            lti_1p3_internal_private_key="",
            lti_1p3_internal_private_key_id="",
            lti_1p3_internal_public_jwk="",
            lti_1p3_client_id="",
            lti_1p3_tool_public_key="",
            lti_1p3_tool_keyset_url="",
        )
        self.duplicate = self.passport(
            name="Passport",
            lti_1p3_client_id="client-id",
            lti_1p3_tool_public_key="tool-public-key",
        )
        self.plain_placement = self.placement(
            self.plain, location="block-v1:org+course+run+type@lti+block@plain"
        )
        # UsageKeyField stores None as an empty string, so only one row may omit the unique location.
        self.shared_placements = [
            self.placement(self.shared, location="block-v1:org+course+run+type@lti+block@shared"),
            self.placement(
                self.shared,
                config_store="CONFIG_EXTERNAL",
                location="block-v1:org+course+run+type@lti+block@external",
            ),
            self.placement(self.shared),
        ]
        self.unlinked = self.placement(None, location="block-v1:org+course+run+type@lti+block@unlinked")
        self.legacy = self.placement(
            None,
            version="lti_1p1",
            config_store="CONFIG_ON_DB",
            location="block-v1:org+course+run+type@lti+block@legacy",
        )

    def passport(self, **overrides):
        """Create a passport with complete, non-default values."""
        values = {
            "passport_id": uuid.uuid4(),
            "name": "Passport",
            "context_key": "course-v1:org+course+run",
            "lti_1p3_internal_private_key": "private-key",
            "lti_1p3_internal_private_key_id": "key-id",
            "lti_1p3_internal_public_jwk": '{"kty": "RSA"}',
            "lti_1p3_client_id": "client-id",
            "lti_1p3_tool_public_key": "",
            "lti_1p3_tool_keyset_url": "https://tool.example/jwks.json",
        }
        values.update(overrides)
        return self.Passport.objects.create(**values)

    def placement(self, passport, **overrides):
        """Create a placement, optionally bound to a passport."""
        values = {
            "config_id": uuid.uuid4(),
            "version": "lti_1p3",
            "config_store": "CONFIG_ON_XBLOCK",
            "lti_1p3_passport": passport,
        }
        values.update(overrides)
        return self.Placement.objects.create(**values)

    def migrate(self, target):
        """Migrate to one target and return the historical apps at that state."""
        self.executor.loader.build_graph()
        self.executor.migrate([target])
        return self.executor.loader.project_state([target]).apps

    def run_copy(self):
        """Run the copy migration and return its historical apps."""
        return self.migrate(COPY_MIGRATION)

    def destination_model(self):
        """Return the destination model from the schema migration state."""
        apps = self.executor.loader.project_state([SCHEMA_MIGRATION]).apps
        return apps.get_model("lti_consumer", "ReusableLtiConfiguration")

    def placement_model(self):
        """Return the placement model that owns the added foreign key."""
        apps = self.executor.loader.project_state([SCHEMA_MIGRATION]).apps
        return apps.get_model("lti_consumer", "LtiConfiguration")

    def assert_recorder_stopped_at_schema(self):
        """The failed copy must not be recorded, and the schema migration must stay applied."""
        self.executor.loader.build_graph()
        self.assertIn(SCHEMA_MIGRATION, self.executor.loader.applied_migrations)
        self.assertNotIn(COPY_MIGRATION, self.executor.loader.applied_migrations)

    def remove_copy(self, copy_pk):
        """Targeted cleanup: unbind and delete one authored destination row."""
        self.placement_model().objects.using(connection.alias).filter(
            reusable_configuration_id=copy_pk
        ).update(reusable_configuration=None)
        self.destination_model().objects.using(connection.alias).filter(pk=copy_pk).delete()

    def clear_binding(self, placement_pk):
        """Targeted cleanup: clear one authored wrong binding."""
        self.placement_model().objects.using(connection.alias).filter(pk=placement_pk).update(
            reusable_configuration=None
        )


class Test0025CopyPassports(PassportCopyHarness):
    """The copy migration preserves every eligible passport and links bound non-1.1 placements."""

    def test_copy_is_lossless_and_keeps_the_old_tables_intact(self):
        old_passports = list(self.Passport.objects.order_by("pk").values())
        old_placements = list(self.Placement.objects.order_by("pk").values())

        with mock.patch("lti_consumer.models.RSA.generate") as rsa, \
                mock.patch("lti_consumer.plugin.compat.load_enough_xblock") as modulestore, \
                mock.patch("lti_consumer.models.get_external_config_from_filter") as provider:
            apps = self.run_copy()

        rsa.assert_not_called()
        modulestore.assert_not_called()
        provider.assert_not_called()

        Reusable = apps.get_model("lti_consumer", "ReusableLtiConfiguration")
        Placement = apps.get_model("lti_consumer", "LtiConfiguration")
        copies = {copy.passport_id: copy for copy in Reusable.objects.all()}
        # The harness orphan and the unplaced duplicate have no link, so they get no
        # copy; their legacy rows must still exist.
        orphans = (self.orphan, self.duplicate)
        copied = [row for row in old_passports if row["id"] not in {orphan.pk for orphan in orphans}]
        self.assertEqual(len(copies), len(copied))
        self.assertEqual(self.Passport.objects.count(), len(old_passports))
        for orphan in orphans:
            self.assertFalse(Reusable.objects.filter(passport_id=orphan.passport_id).exists())

        for old in copied:
            copy = copies[old["passport_id"]]
            for field in PRESERVED_FIELDS:
                self.assertEqual(getattr(copy, field), old[field], field)

        # Only the new row gets the inferred canonical key; the old table keeps the raw one.
        self.assertEqual(copies[self.plain.passport_id].context_key, "course-v1:org+course+run")
        self.assertEqual(self.Passport.objects.get(pk=self.plain.pk).context_key, self.plain.context_key)
        self.assertEqual(copies[self.shared.passport_id].context_key, "")
        self.assertEqual(self.Passport.objects.get(pk=self.shared.pk).context_key, self.shared.context_key)

        for old in old_placements:
            placement = Placement.objects.get(pk=old["id"])
            # Every historical column is unchanged; only the added FK is new.
            for field in old:
                self.assertEqual(getattr(placement, field), old[field], field)

        self.assertEqual(copies[self.plain.passport_id].passport_id, self.plain.passport_id)
        self.assertNotEqual(self.plain.passport_id, self.plain_placement.config_id)
        self.assertFalse(Reusable.objects.filter(passport_id=self.plain_placement.config_id).exists())

        linked = dict(Placement.objects.values_list("pk", "reusable_configuration_id"))
        for old in old_placements:
            if old["lti_1p3_passport_id"] is None:
                self.assertIsNone(linked[old["id"]])
                continue
            source = next(row for row in old_passports if row["id"] == old["lti_1p3_passport_id"])
            self.assertEqual(linked[old["id"]], copies[source["passport_id"]].pk)

        # An LTI 1.1 placement with no old FK stays unlinked, as before.
        self.assertIsNone(linked[self.legacy.pk])
        self.assertEqual(Placement.objects.get(pk=self.legacy.pk).version, "lti_1p1")

        # Inference is covered by the matrix; every other unsourced field keeps its default.
        copy = Reusable.objects.get(passport_id=self.plain.passport_id)
        self.assertIsNone(copy.lti_1p3_tool_key_mode)
        self.assertIsNone(copy.lti_1p1_launch_url)
        self.assertIsNone(copy.lti_1p1_client_key)
        self.assertIsNone(copy.lti_1p1_client_secret)
        self.assertEqual(copy.description, "")
        self.assertEqual(copy.display_name, "LTI Consumer")
        self.assertFalse(copy.enable_grading)
        self.assertEqual(copy.grade_weight, 1.0)
        self.assertTrue(copy.accept_grades_after_due_date)
        self.assertEqual(copy.open_tool_in, "iframe")
        self.assertEqual(copy.inline_height, 800)
        self.assertEqual(copy.modal_height, 80)
        self.assertEqual(copy.modal_width, 80)
        self.assertEqual(copy.launch_button_text, "")
        self.assertFalse(copy.send_extra_parameters)
        self.assertEqual(copy.lti_1p3_redirect_uris, [])
        self.assertEqual(copy.custom_parameters, [])
        self.assertFalse(copy.lti_advantage_deep_linking_enabled)
        self.assertEqual(copy.lti_advantage_ags_mode, "declarative")
        self.assertFalse(copy.lti_advantage_enable_nrps)
        self.assertIsNotNone(copy.created_at)
        self.assertIsNotNone(copy.updated_at)
        # Every copied configuration starts active.
        self.assertFalse(Reusable.objects.filter(is_active=False).exists())

    def test_batches_cover_every_linked_passport(self):
        """Every linked passport is copied, including those in later batches."""
        extra = [
            self.Passport(passport_id=uuid.uuid4(), name=f"Bulk {index}", lti_1p3_client_id=f"bulk-{index}")
            for index in range(501)
        ]
        self.Passport.objects.bulk_create(extra)
        # Each source needs a link, otherwise it is an orphan and is skipped.
        self.Placement.objects.bulk_create([
            self.Placement(
                config_id=uuid.uuid4(),
                version="lti_1p3",
                config_store="CONFIG_ON_XBLOCK",
                location=f"block-v1:org+course+run+type@lti+block@bulk-{index}",
                lti_1p3_passport=passport,
            )
            for index, passport in enumerate(
                self.Passport.objects.filter(name__startswith="Bulk ").order_by("pk")
            )
        ])

        apps = self.run_copy()
        Reusable = apps.get_model("lti_consumer", "ReusableLtiConfiguration")
        bulk_ids = set(
            self.Passport.objects.filter(name__startswith="Bulk ").values_list("passport_id", flat=True)
        )
        self.assertEqual(len(bulk_ids), 501)
        self.assertEqual(bulk_ids - set(Reusable.objects.values_list("passport_id", flat=True)), set())

    def test_new_table_identity_and_binding_contract(self):
        apps = self.run_copy()
        Reusable = apps.get_model("lti_consumer", "ReusableLtiConfiguration")
        Placement = apps.get_model("lti_consumer", "LtiConfiguration")

        self.assertEqual(Reusable._meta.pk.name, "id")

        new_fk = Placement._meta.get_field("reusable_configuration")
        self.assertIs(new_fk.remote_field.on_delete, models.PROTECT)
        self.assertTrue(new_fk.null)
        self.assertTrue(new_fk.blank)
        self.assertEqual(new_fk.target_field.name, "id")

        self.assertEqual(
            sorted(constraint.name for constraint in Reusable._meta.constraints),
            ["reusable_context_key_shape", "reusable_context_type_valid"],
        )
        self.assertEqual([index.name for index in Reusable._meta.indexes], ["reusable_context_lookup"])
        self.assertEqual(list(Reusable._meta.indexes[0].fields), ["context_type", "context_key"])

        active = Reusable._meta.get_field("is_active")
        self.assertFalse(active.null)
        self.assertTrue(active.get_default())


class Test0025ReplayAndReuse(PassportCopyHarness):
    """Reusing or replaying a copy keeps its values and later edits."""

    def seed(self):
        self.plain = self.passport()
        self.shared = self.passport(name="Shared", lti_1p3_client_id="shared-client")
        # Unlinked, so it is skipped unless a copy already exists.
        self.orphan = self.passport(
            name="Orphan", lti_1p3_tool_public_key="", lti_1p3_tool_keyset_url=""
        )
        self.plain_placement = self.placement(
            self.plain, location="block-v1:org+course+run+type@lti+block@replay-plain"
        )
        self.shared_placement = self.placement(
            self.shared, location="block-v1:org+course+run+type@lti+block@replay-shared"
        )

    def assert_replayed(self, apps, phase, snapshot):
        """Assert a reverse or replay kept rows, links and the edited copy."""
        pk_by_passport, linked_before, shared_pk = snapshot
        Reusable = apps.get_model("lti_consumer", "ReusableLtiConfiguration")
        Placement = apps.get_model("lti_consumer", "LtiConfiguration")
        self.assertEqual({copy.passport_id: copy.pk for copy in Reusable.objects.all()}, pk_by_passport, phase)
        self.assertEqual(dict(Placement.objects.values_list("pk", "reusable_configuration_id")), linked_before, phase)
        shared = Reusable.objects.get(pk=shared_pk)
        self.assertIsNone(shared.version, phase)
        self.assertEqual(shared.context_type, "site", phase)
        self.assertEqual(shared.context_key, "", phase)
        self.assertEqual(shared.description, "Edited after the copy", phase)
        self.assertEqual(
            Placement.objects.get(pk=self.shared_placement.pk).reusable_configuration_id, shared_pk, phase
        )

    def test_replay_reuses_copies_without_refreshing_or_comparing_inferred_fields(self):
        apps = self.migrate(SCHEMA_MIGRATION)
        Reusable = apps.get_model("lti_consumer", "ReusableLtiConfiguration")
        values = {field: getattr(self.plain, field) for field in PASSPORT_FIELDS}
        # Existing copies must keep these values unset.
        preexisting = Reusable.objects.create(
            **values,
            description="Hand-written catalog note",
            display_name="Custom name",
        )
        preexisting_pk = preexisting.pk
        # An unlinked passport with an existing copy is reused, never skipped or refreshed.
        authored = Reusable.objects.create(
            **{field: getattr(self.orphan, field) for field in PASSPORT_FIELDS},
            description="Authored note",
            display_name="Authored",
        )
        authored_pk = authored.pk

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            apps = self.run_copy()
        Reusable = apps.get_model("lti_consumer", "ReusableLtiConfiguration")
        Placement = apps.get_model("lti_consumer", "LtiConfiguration")
        counts = output.getvalue()

        # Both existing copies are reused as-is; only the shared passport is inserted.
        self.assertIn("reused=2", counts)
        self.assertIn("inserted=1", counts)
        self.assertIn("skipped=0", counts)

        self.assertEqual(Reusable.objects.count(), 3)
        reused = Reusable.objects.get(passport_id=self.plain.passport_id)
        self.assertEqual(reused.pk, preexisting_pk)
        self.assertEqual(reused.description, "Hand-written catalog note")
        self.assertEqual(reused.display_name, "Custom name")
        self.assertIsNone(reused.version)
        self.assertIsNone(reused.context_type)
        self.assertEqual(reused.context_key, self.plain.context_key)

        orphan_copy = Reusable.objects.get(passport_id=self.orphan.passport_id)
        self.assertEqual(orphan_copy.pk, authored_pk)
        self.assertEqual(orphan_copy.description, "Authored note")
        self.assertEqual(orphan_copy.display_name, "Authored")
        self.assertIsNone(orphan_copy.version)
        self.assertIsNone(orphan_copy.context_type)

        # The shared passport is new, so it does get inferred metadata.
        shared_copy = Reusable.objects.get(passport_id=self.shared.passport_id)
        self.assertEqual(shared_copy.version, "lti_1p3")
        self.assertEqual(shared_copy.context_type, "course")
        self.assertEqual(shared_copy.context_key, "course-v1:org+course+run")
        self.assertEqual(
            Placement.objects.get(pk=self.plain_placement.pk).reusable_configuration_id,
            preexisting_pk,
        )

        # Edit the new copy and the old raw keys.
        # Replay must keep the edits without comparing those keys.
        Reusable.objects.filter(pk=shared_copy.pk).update(
            version=None, context_type="site", context_key="", description="Edited after the copy"
        )
        self.Passport.objects.filter(pk__in=[self.plain.pk, self.shared.pk]).update(
            context_key="changed raw key"
        )

        snapshot = (
            {copy.passport_id: copy.pk for copy in Reusable.objects.all()},
            dict(Placement.objects.values_list("pk", "reusable_configuration_id")),
            shared_copy.pk,
        )

        # The data-only reverse is a noop: rows, links and edited data survive, and the
        # copy migration is really unapplied.
        apps = self.migrate(SCHEMA_MIGRATION)
        self.executor.loader.build_graph()
        self.assertIn(SCHEMA_MIGRATION, self.executor.loader.applied_migrations)
        self.assertNotIn(COPY_MIGRATION, self.executor.loader.applied_migrations)
        self.assert_replayed(apps, "noop reverse", snapshot)

        # The replay must really run again, not be skipped as already applied.
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            apps = self.run_copy()
        self.assertIn("reused=3", output.getvalue())
        self.assertIn("inserted=0", output.getvalue())
        self.executor.loader.build_graph()
        self.assertIn(COPY_MIGRATION, self.executor.loader.applied_migrations)
        self.assert_replayed(apps, "replay", snapshot)

        Reusable = apps.get_model("lti_consumer", "ReusableLtiConfiguration")
        reused = Reusable.objects.get(passport_id=self.plain.passport_id)
        self.assertEqual(reused.description, "Hand-written catalog note")
        self.assertIsNone(reused.version)
        self.assertIsNone(reused.context_type)
        orphan_copy = Reusable.objects.get(passport_id=self.orphan.passport_id)
        self.assertEqual(orphan_copy.pk, authored_pk)
        self.assertEqual(orphan_copy.description, "Authored note")
        self.assertEqual(orphan_copy.display_name, "Authored")
        self.assertIsNone(orphan_copy.version)
        self.assertIsNone(orphan_copy.context_type)


class Test0025Inference(PassportCopyHarness):
    """Inference reads eligible placements through the old FK, for new copies only."""

    def seed(self):
        self.cases = {}
        self.case(
            "one-course",
            ("lti_1p3", "CONFIG_ON_XBLOCK", "block-v1:EdX+Demo+2024+type@lti+block@one-course-a"),
            ("lti_1p3", "CONFIG_ON_XBLOCK", "block-v1:EdX+Demo+2024+type@lti+block@one-course-b"),
        )
        self.case(
            "unanimous-1p1",
            ("lti_1p1", "CONFIG_ON_XBLOCK", "block-v1:EdX+Demo+Legacy+type@lti+block@unanimous-a"),
            ("lti_1p1", "CONFIG_ON_DB", "block-v1:EdX+Demo+Legacy+type@lti+block@unanimous-b"),
            tool_keys=True,
        )
        self.case(
            "unanimous-1p1-empty-tools",
            ("lti_1p1", "CONFIG_ON_XBLOCK", "block-v1:EdX+Demo+Placeholder+type@lti+block@placeholder-a"),
            ("lti_1p1", "CONFIG_ON_DB", "block-v1:EdX+Demo+Placeholder+type@lti+block@placeholder-b"),
            tool_keys=False,
        )
        self.case(
            "mixed-version",
            ("lti_1p1", "CONFIG_ON_XBLOCK", "block-v1:EdX+Demo+Mixed+type@lti+block@mixed-1p1"),
            ("lti_1p3", "CONFIG_ON_XBLOCK", "block-v1:EdX+Demo+Mixed+type@lti+block@mixed-1p3"),
        )
        self.case(
            "invalid-version",
            ("lti_4p0", "CONFIG_ON_XBLOCK", "block-v1:EdX+Demo+Invalid+type@lti+block@invalid"),
        )
        self.case(
            "blank-version",
            ("", "CONFIG_ON_XBLOCK", "block-v1:EdX+Demo+Blank+type@lti+block@blank"),
        )
        self.case(
            "external-only",
            ("lti_1p3", CONFIG_EXTERNAL, "block-v1:EdX+External+2024+type@lti+block@external-only"),
        )
        self.case(
            "external-ignored",
            ("lti_1p1", "CONFIG_ON_XBLOCK", "block-v1:EdX+Demo+External+type@lti+block@internal"),
            ("lti_1p3", CONFIG_EXTERNAL, "block-v1:EdX+External+2024+type@lti+block@external-ignored"),
        )
        self.case(
            "external-1p1",
            ("lti_1p1", "CONFIG_ON_XBLOCK", "block-v1:EdX+Demo+ExternalOne+type@lti+block@internal"),
            ("lti_1p1", CONFIG_EXTERNAL, "block-v1:EdX+External+2024+type@lti+block@external-1p1"),
            tool_keys=False,
        )
        self.case(
            "organization",
            ("lti_1p3", "CONFIG_ON_XBLOCK", "block-v1:Org+Alpha+Run+type@lti+block@organization-a"),
            ("lti_1p3", "CONFIG_ON_XBLOCK", "block-v1:ORG+Beta+Run+type@lti+block@organization-b"),
        )
        self.case(
            "cross-organization",
            ("lti_1p3", "CONFIG_ON_XBLOCK", "block-v1:OrgA+Alpha+Run+type@lti+block@cross-a"),
            ("lti_1p3", "CONFIG_ON_XBLOCK", "block-v1:OrgB+Beta+Run+type@lti+block@cross-b"),
        )
        self.case(
            "library",
            ("lti_1p3", "CONFIG_ON_XBLOCK", "lib-block-v1:Org+Library+Run+type@lti+block@library"),
        )
        self.case(
            "ccx",
            ("lti_1p3", "CONFIG_ON_XBLOCK", "ccx-block-v1:Org+CCX+Run+ccx@1+type@lti+block@ccx"),
        )
        self.case(
            "course-and-library",
            ("lti_1p3", "CONFIG_ON_XBLOCK", "block-v1:EdX+Demo+Library+type@lti+block@course"),
            ("lti_1p3", "CONFIG_ON_XBLOCK", "lib-block-v1:Org+Library+Run+type@lti+block@course-and-library"),
        )
        self.case(
            "missing-location",
            ("lti_1p3", "CONFIG_ON_XBLOCK", "block-v1:EdX+Demo+Missing+type@lti+block@present"),
            # UsageKeyField stores None as an empty string, so this is the only missing location.
            ("lti_1p3", "CONFIG_ON_DB", None),
        )
        self.case("no-placements")

    def case(self, name, *placements, context_key="raw legacy key", tool_keys=False):
        """Create a passport and its placements; saved tool keys stay opt-in.

        Most fixtures save no tool key material, so each one also guards the copy
        eligibility rule. A passport without placements is an orphan and gets no
        copy. The copy is checked later.
        """
        values = {"name": name, "context_key": context_key}
        if not tool_keys:
            values.update(lti_1p3_tool_public_key="", lti_1p3_tool_keyset_url="")
        passport = self.passport(**values)
        for version, config_store, location in placements:
            self.placement(passport, version=version, config_store=config_store, location=location)
        self.cases[name] = passport

    def test_inference_matrix(self):
        apps = self.run_copy()
        Reusable = apps.get_model("lti_consumer", "ReusableLtiConfiguration")
        Placement = apps.get_model("lti_consumer", "LtiConfiguration")

        expected = {
            "one-course": ("lti_1p3", "course", "course-v1:EdX+Demo+2024"),
            "unanimous-1p1": ("lti_1p1", "course", "course-v1:EdX+Demo+Legacy"),
            "mixed-version": (None, "course", "course-v1:EdX+Demo+Mixed"),
            "invalid-version": (None, "course", "course-v1:EdX+Demo+Invalid"),
            "blank-version": (None, "course", "course-v1:EdX+Demo+Blank"),
            "external-only": (None, "site", ""),
            "external-ignored": ("lti_1p1", "course", "course-v1:EdX+Demo+External"),
            "organization": ("lti_1p3", "organization", "org"),
            "cross-organization": ("lti_1p3", "site", ""),
            "library": ("lti_1p3", "site", ""),
            "ccx": ("lti_1p3", "site", ""),
            "course-and-library": ("lti_1p3", "site", ""),
            "missing-location": ("lti_1p3", "site", ""),
            "external-1p1": ("lti_1p1", "course", "course-v1:EdX+Demo+ExternalOne"),
        }
        skipped = ("unanimous-1p1-empty-tools", "no-placements")
        self.assertEqual(set(expected) | set(skipped), set(self.cases))
        for name, fields in expected.items():
            with self.subTest(case=name):
                copy = Reusable.objects.get(passport_id=self.cases[name].passport_id)
                self.assertEqual((copy.version, copy.context_type, copy.context_key), fields)
        for name in skipped:
            with self.subTest(case=name):
                passport = self.cases[name]
                self.assertFalse(Reusable.objects.filter(passport_id=passport.passport_id).exists())
                self.assertFalse(
                    Placement.objects.filter(
                        lti_1p3_passport_id=passport.pk,
                        reusable_configuration__isnull=False,
                    ).exists()
                )

        # The old table keeps the raw key; only the new row gets the canonical one.
        self.assertEqual(self.cases["one-course"].context_key, "raw legacy key")
        self.assertEqual(
            self.Passport.objects.get(pk=self.cases["one-course"].pk).context_key, "raw legacy key"
        )

        # Skip external placements for inference, but still link them.
        external = Placement.objects.get(lti_1p3_passport_id=self.cases["external-only"].pk)
        self.assertEqual(
            external.reusable_configuration_id,
            Reusable.objects.get(passport_id=self.cases["external-only"].passport_id).pk,
        )

        # Known internal 1.1 placements are never newly bound, even where the copy is kept.
        for name in ("unanimous-1p1", "mixed-version", "external-1p1", "external-ignored"):
            with self.subTest(case=name):
                self.assertFalse(
                    Placement.objects.filter(
                        lti_1p3_passport_id=self.cases[name].pk,
                        config_store__in=("CONFIG_ON_XBLOCK", "CONFIG_ON_DB"),
                        version="lti_1p1",
                        reusable_configuration__isnull=False,
                    ).exists()
                )

        # Non-1.1 internal placements still link to the copy that was kept.
        mixed_copy = Reusable.objects.get(passport_id=self.cases["mixed-version"].passport_id)
        self.assertEqual(
            Placement.objects.get(
                lti_1p3_passport_id=self.cases["mixed-version"].pk, version="lti_1p3"
            ).reusable_configuration_id,
            mixed_copy.pk,
        )
        blank_version_link = Placement.objects.get(
            lti_1p3_passport_id=self.cases["blank-version"].pk
        )
        self.assertIsNotNone(blank_version_link.reusable_configuration_id)

        # External placements keep their existing linking behaviour.
        for name in ("external-ignored", "external-1p1"):
            with self.subTest(case=name):
                external = Placement.objects.get(
                    lti_1p3_passport_id=self.cases[name].pk, config_store=CONFIG_EXTERNAL
                )
                self.assertEqual(
                    external.reusable_configuration_id,
                    Reusable.objects.get(passport_id=self.cases[name].passport_id).pk,
                )


class Test0025InferencePages(PassportCopyHarness):
    """Inference covers every placement page, not just the first batch."""

    def seed(self):
        self.source = self.passport(name="Paged")
        first_page = [
            self.Placement(
                config_id=uuid.uuid4(),
                version="lti_1p3",
                config_store="CONFIG_ON_XBLOCK",
                location=f"block-v1:OrgA+Alpha+Run+type@lti+block@page-one-{index}",
                lti_1p3_passport=self.source,
            )
            for index in range(500)
        ]
        self.Placement.objects.bulk_create(first_page, batch_size=500)
        # Only the second page disagrees; reading the first alone would infer lti_1p3/course.
        self.disagreement = self.placement(
            self.source,
            version="lti_1p1",
            location="block-v1:OrgB+Beta+Run+type@lti+block@page-two",
        )

    def test_inference_includes_placements_after_the_first_page(self):
        apps = self.run_copy()
        Reusable = apps.get_model("lti_consumer", "ReusableLtiConfiguration")
        Placement = apps.get_model("lti_consumer", "LtiConfiguration")
        copy = Reusable.objects.get(passport_id=self.source.passport_id)

        self.assertEqual(Placement.objects.filter(lti_1p3_passport_id=self.source.pk).count(), 501)
        self.assertEqual((copy.version, copy.context_type, copy.context_key), (None, "site", ""))
        # The 1.1 placement stays unbound even though the shared copy is kept.
        self.assertIsNone(Placement.objects.get(pk=self.disagreement.pk).reusable_configuration_id)


class Test0025SkippedPassports(PassportCopyHarness):
    """Passports nothing can reach, or confirmed LTI 1.1-only placeholders, get no copy."""

    def seed(self):
        # Confirmed LTI 1.1-only placeholder: linked, internal and no saved tool keys.
        self.placeholder = self.passport(
            name=None,
            context_key=None,
            lti_1p3_internal_private_key="",
            lti_1p3_internal_private_key_id="",
            lti_1p3_internal_public_jwk="",
            lti_1p3_client_id="",
            lti_1p3_tool_public_key="",
            lti_1p3_tool_keyset_url="",
        )
        self.placeholder_placements = [
            self.placement(
                self.placeholder,
                version="lti_1p1",
                location="block-v1:org+course+run+type@lti+block@placeholder-a",
            ),
            self.placement(
                self.placeholder,
                version="lti_1p1",
                config_store="CONFIG_ON_DB",
                location="block-v1:org+course+run+type@lti+block@placeholder-b",
            ),
        ]
        # Orphans: no placement points at them, with and without saved tool keys.
        self.orphan_blank = self.passport(
            name="Orphan blank",
            context_key=None,
            lti_1p3_tool_public_key="",
            lti_1p3_tool_keyset_url="",
        )
        self.orphan_saved = self.passport(
            name="Orphan saved",
            lti_1p3_tool_public_key="tool-public-key",
            lti_1p3_tool_keyset_url="https://tool.example/jwks.json",
        )
        # An external placement is still a link, so this passport keeps its copy.
        self.external = self.passport(
            name="External only", lti_1p3_tool_public_key="", lti_1p3_tool_keyset_url=""
        )
        self.external_placement = self.placement(
            self.external,
            version="lti_1p3",
            config_store=CONFIG_EXTERNAL,
            location="block-v1:org+course+run+type@lti+block@orphan-external",
        )
        # Saved tool keys keep the copy even when every link is internal LTI 1.1.
        self.public_key = self.passport(
            lti_1p3_tool_public_key="tool-public-key",
            lti_1p3_tool_keyset_url="",
        )
        self.public_key_placement = self.placement(
            self.public_key,
            version="lti_1p1",
            location="block-v1:org+course+run+type@lti+block@public-key",
        )
        # The passports that get no copy, with the placements that must stay as they are.
        self.skipped = (
            ("placeholder", self.placeholder, self.placeholder_placements),
            ("orphan_blank", self.orphan_blank, ()),
            ("orphan_saved", self.orphan_saved, ()),
        )

    def passport_values(self, passport):
        """Return every stored legacy passport value for an untouched-row check."""
        return self.Passport.objects.filter(pk=passport.pk).values().get()

    def snapshots(self):
        """Snapshot the legacy rows that must never change."""
        return {label: self.passport_values(passport) for label, passport, _placements in self.skipped}

    def assert_skipped_untouched(self, Reusable, Placement, snapshots, bound=None):
        """Skipped passports keep their legacy rows and the placements keep their FKs.

        The optional bound mapping names the one authored configuration a placement may
        still point at.
        """
        bound = bound or {}
        for label, passport, placements in self.skipped:
            with self.subTest(skipped=label):
                self.assertFalse(Reusable.objects.filter(passport_id=passport.passport_id).exists())
                self.assertEqual(self.passport_values(passport), snapshots[label])
                for placement in placements:
                    stored = Placement.objects.get(pk=placement.pk)
                    self.assertEqual(stored.lti_1p3_passport_id, passport.pk)
                    self.assertEqual(stored.reusable_configuration_id, bound.get(placement.pk))

    def assert_kept_copies(self, Reusable, Placement, public_key_pk):
        """A kept copy carries its legacy values and never binds an internal LTI 1.1 placement."""
        external_copy = Reusable.objects.get(passport_id=self.external.passport_id)
        self.assertEqual(external_copy.lti_1p3_client_id, self.external.lti_1p3_client_id)
        self.assertEqual(
            Placement.objects.get(pk=self.external_placement.pk).reusable_configuration_id,
            external_copy.pk,
        )
        copy = Reusable.objects.get(passport_id=self.public_key.passport_id)
        self.assertEqual(copy.pk, public_key_pk)
        self.assertEqual(copy.lti_1p3_tool_public_key, "tool-public-key")
        self.assertIsNone(
            Placement.objects.get(pk=self.public_key_placement.pk).reusable_configuration_id
        )

    def test_ineligible_passports_are_skipped_and_survive_replay(self):
        snapshots = self.snapshots()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            apps = self.run_copy()
        Reusable = apps.get_model("lti_consumer", "ReusableLtiConfiguration")
        Placement = apps.get_model("lti_consumer", "LtiConfiguration")

        self.assertIn("skipped=3", output.getvalue())
        self.assert_skipped_untouched(Reusable, Placement, snapshots)
        # A preserved tool-key passport is still copied, but its 1.1 placement is not bound.
        kept_pk = Reusable.objects.get(passport_id=self.public_key.passport_id).pk
        self.assert_kept_copies(Reusable, Placement, kept_pk)

        # The data reverse is a no-op: skipped passports stay absent, kept copies survive,
        # and the replay neither creates nor re-binds anything.
        self.migrate(SCHEMA_MIGRATION)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            apps = self.run_copy()
        Reusable = apps.get_model("lti_consumer", "ReusableLtiConfiguration")
        Placement = apps.get_model("lti_consumer", "LtiConfiguration")
        counts = output.getvalue()
        self.assertIn("inserted=0", counts)
        self.assertIn("skipped=3", counts)
        self.assertIn("reused=2", counts)
        self.assert_skipped_untouched(Reusable, Placement, snapshots)
        self.assert_kept_copies(Reusable, Placement, kept_pk)

    def test_prebound_lti1p1_placements_are_preserved_then_abort_and_retry(self):
        snapshots = self.snapshots()
        apps = self.migrate(SCHEMA_MIGRATION)
        Reusable = apps.get_model("lti_consumer", "ReusableLtiConfiguration")
        Placement = apps.get_model("lti_consumer", "LtiConfiguration")

        # A binding authored on a skipped passport's placement is left exactly as it is.
        authored = Reusable.objects.create(passport_id=uuid.uuid4(), lti_1p3_client_id="authored-client")
        Placement.objects.filter(pk=self.placeholder_placements[0].pk).update(
            reusable_configuration=authored
        )
        authored_binding = {self.placeholder_placements[0].pk: authored.pk}
        self.addCleanup(self.clear_binding, self.placeholder_placements[0].pk)

        apps = self.run_copy()
        Reusable = apps.get_model("lti_consumer", "ReusableLtiConfiguration")
        Placement = apps.get_model("lti_consumer", "LtiConfiguration")
        kept_pk = Reusable.objects.get(passport_id=self.public_key.passport_id).pk

        self.assertEqual(Reusable.objects.count(), 3)
        self.assert_skipped_untouched(Reusable, Placement, snapshots, bound=authored_binding)
        self.assert_kept_copies(Reusable, Placement, kept_pk)

        # A placement bound to a different configuration aborts instead of being overwritten.
        # Reverse the data migration first: it is a no-op that keeps every row, but the replay
        # must really run again to reach the link phase.
        self.migrate(SCHEMA_MIGRATION)
        apps = self.executor.loader.project_state([SCHEMA_MIGRATION]).apps
        Reusable = apps.get_model("lti_consumer", "ReusableLtiConfiguration")
        Placement = apps.get_model("lti_consumer", "LtiConfiguration")
        other = Reusable.objects.create(passport_id=uuid.uuid4(), lti_1p3_client_id="other-client")
        Placement.objects.filter(pk=self.public_key_placement.pk).update(reusable_configuration=other)
        self.addCleanup(self.clear_binding, self.public_key_placement.pk)

        with self.assertRaises(RuntimeError) as caught:
            self.run_copy()

        message = str(caught.exception)
        self.assertIn(str(self.public_key_placement.pk), message)
        self.assertIn(str(other.pk), message)
        self.assertNotIn(self.public_key.lti_1p3_internal_private_key, message)
        self.assert_recorder_stopped_at_schema()
        # Nothing was inserted, re-bound or deleted by the aborted run.
        self.assertEqual(Reusable.objects.count(), 4)
        self.assert_skipped_untouched(Reusable, Placement, snapshots, bound=authored_binding)
        self.assertEqual(
            Placement.objects.get(pk=self.public_key_placement.pk).reusable_configuration_id,
            other.pk,
        )

        # Repair the one authored row and retry: the kept copy is reused and left alone.
        Placement.objects.filter(pk=self.public_key_placement.pk).update(reusable_configuration=None)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            apps = self.run_copy()
        Reusable = apps.get_model("lti_consumer", "ReusableLtiConfiguration")
        Placement = apps.get_model("lti_consumer", "LtiConfiguration")
        counts = output.getvalue()
        self.assertIn("inserted=0", counts)
        self.assertIn("reused=2", counts)
        self.assertIn("skipped=3", counts)
        self.assertEqual(Reusable.objects.count(), 4)
        self.assert_kept_copies(Reusable, Placement, kept_pk)
        self.assert_skipped_untouched(Reusable, Placement, snapshots, bound=authored_binding)


class Test0025LateDivergentCopyAborts(PassportCopyHarness):
    """A divergent copy in a later batch aborts after earlier batches were inserted."""

    def seed(self):
        sources = [
            self.Passport(
                passport_id=uuid.uuid4(),
                name=f"Bulk {index}",
                lti_1p3_client_id=f"bulk-{index}",
                lti_1p3_internal_private_key="private-key",
            )
            for index in range(505)
        ]
        self.Passport.objects.bulk_create(sources, batch_size=500)
        # Every source needs a link, otherwise it is an orphan and would be skipped.
        self.Placement.objects.bulk_create([
            self.Placement(
                config_id=uuid.uuid4(),
                version="lti_1p3",
                config_store="CONFIG_ON_XBLOCK",
                location=f"block-v1:org+course+run+type@lti+block@late-source-{index}",
                lti_1p3_passport=passport,
            )
            for index, passport in enumerate(self.Passport.objects.order_by("pk"))
        ], batch_size=500)
        self.sources = list(self.Passport.objects.order_by("pk"))
        self.early = self.sources[0]
        self.late = self.sources[-1]  # falls in the second batch
        self.early_placement = self.placement(
            self.early, location="block-v1:org+course+run+type@lti+block@late-divergent"
        )

    def test_late_divergent_copy_rolls_back_earlier_batches_and_retry_succeeds(self):
        apps = self.migrate(SCHEMA_MIGRATION)
        Reusable = apps.get_model("lti_consumer", "ReusableLtiConfiguration")
        values = {field: getattr(self.late, field) for field in PASSPORT_FIELDS}
        values["lti_1p3_client_id"] = "divergent-client"
        divergent = Reusable.objects.create(**values)
        self.addCleanup(self.remove_copy, divergent.pk)

        with self.assertRaises(RuntimeError) as caught:
            self.run_copy()

        message = str(caught.exception)
        self.assertIn(str(self.late.passport_id), message)
        self.assertIn("lti_1p3_client_id", message)
        self.assertNotIn(self.late.lti_1p3_internal_private_key, message)
        # The first batch of 500 inserts ran before the second batch hit the conflict.
        self.assertRegex(message, r"inserted[^0-9]{0,20}500")

        # Only the preseeded divergent row survives; every earlier insert rolled back.
        self.assertEqual(Reusable.objects.count(), 1)
        self.assertEqual(Reusable.objects.get().pk, divergent.pk)
        self.assertEqual(self.Passport.objects.count(), 505)
        self.assertEqual(
            self.Passport.objects.get(pk=self.early.pk).lti_1p3_client_id, self.early.lti_1p3_client_id
        )
        self.assertEqual(
            self.Placement.objects.get(pk=self.early_placement.pk).lti_1p3_passport_id, self.early.pk
        )
        self.assert_recorder_stopped_at_schema()

        Reusable.objects.filter(pk=divergent.pk).update(lti_1p3_client_id=self.late.lti_1p3_client_id)
        apps = self.run_copy()
        Reusable = apps.get_model("lti_consumer", "ReusableLtiConfiguration")
        Placement = apps.get_model("lti_consumer", "LtiConfiguration")
        self.assertEqual(Reusable.objects.count(), 505)
        self.assertEqual(Reusable.objects.get(passport_id=self.late.passport_id).pk, divergent.pk)
        self.assertEqual(
            Placement.objects.get(pk=self.early_placement.pk).reusable_configuration_id,
            Reusable.objects.get(passport_id=self.early.passport_id).pk,
        )


class Test0025LateWrongBindingAborts(PassportCopyHarness):
    """A wrong binding in a later batch aborts after earlier links were applied."""

    def seed(self):
        self.passport_obj = self.passport()
        placements = [
            self.Placement(
                config_id=uuid.uuid4(),
                version="lti_1p3",
                config_store="CONFIG_ON_XBLOCK",
                location=f"block-v1:org+course+run+type@lti+block@late-binding-{index}",
                lti_1p3_passport=self.passport_obj,
            )
            for index in range(505)
        ]
        self.Placement.objects.bulk_create(placements, batch_size=500)
        self.placements = list(self.Placement.objects.order_by("pk"))
        self.early_placement = self.placements[0]
        self.late_placement = self.placements[-1]  # falls in the second batch

    def test_late_wrong_binding_rolls_back_inserts_and_earlier_links(self):
        apps = self.migrate(SCHEMA_MIGRATION)
        Reusable = apps.get_model("lti_consumer", "ReusableLtiConfiguration")
        Placement = apps.get_model("lti_consumer", "LtiConfiguration")
        other = Reusable.objects.create(passport_id=uuid.uuid4(), lti_1p3_client_id="other-client")
        Placement.objects.filter(pk=self.late_placement.pk).update(reusable_configuration=other)
        self.addCleanup(self.clear_binding, self.late_placement.pk)

        with self.assertRaises(RuntimeError) as caught:
            self.run_copy()

        message = str(caught.exception)
        self.assertIn(str(self.late_placement.pk), message)
        self.assertIn(str(other.pk), message)
        self.assertNotIn(self.passport_obj.lti_1p3_internal_private_key, message)
        # The first batch of 500 placements was linked before the second batch aborted.
        self.assertRegex(message, r"linked[^0-9]{0,20}500")

        # Every insert and every earlier link rolled back; the authored target is untouched.
        self.assertEqual(Reusable.objects.count(), 1)
        self.assertEqual(Reusable.objects.get().pk, other.pk)
        self.assertEqual(Reusable.objects.get().lti_1p3_client_id, "other-client")
        self.assertIsNone(Placement.objects.get(pk=self.early_placement.pk).reusable_configuration_id)
        self.assertEqual(
            Placement.objects.get(pk=self.late_placement.pk).reusable_configuration_id, other.pk
        )
        self.assertEqual(
            Placement.objects.filter(lti_1p3_passport_id=self.passport_obj.pk).count(), 505
        )
        self.assert_recorder_stopped_at_schema()

        Placement.objects.filter(pk=self.late_placement.pk).update(reusable_configuration=None)
        apps = self.run_copy()
        Reusable = apps.get_model("lti_consumer", "ReusableLtiConfiguration")
        Placement = apps.get_model("lti_consumer", "LtiConfiguration")
        copy = Reusable.objects.get(passport_id=self.passport_obj.passport_id)
        self.assertEqual(Reusable.objects.count(), 2)
        self.assertEqual(Placement.objects.filter(reusable_configuration=copy).count(), 505)


class Test0025ContentTypes(PassportCopyHarness):
    """The real migrate command creates the new content type and keeps the old permissions."""

    NEW_CONTENT_TYPE = {"app_label": "lti_consumer", "model": "reusablelticonfiguration"}
    OLD_CONTENT_TYPE = {"app_label": "lti_consumer", "model": "lti1p3passport"}

    def test_real_migrate_creates_new_content_type_and_keeps_old_permissions(self):
        call_command(
            "migrate", "lti_consumer", "0023_lti1p3passport_context_key_lti1p3passport_name_and_more", verbosity=0
        )

        # Drop only a stale new content type left by an earlier migrate of this disposable database.
        stale = ContentType.objects.filter(**self.NEW_CONTENT_TYPE).first()
        if stale is not None:
            stale.delete()
        self.assertFalse(ContentType.objects.filter(**self.NEW_CONTENT_TYPE).exists())

        # Natural-key lookup: this must not create the new content type.
        old_ct = ContentType.objects.get(**self.OLD_CONTENT_TYPE)
        old_permission_ids = set(
            Permission.objects.filter(content_type=old_ct).values_list("id", flat=True)
        )
        self.assertTrue(old_permission_ids)
        group = Group.objects.create(name="passport-readers")
        group.permissions.set(old_permission_ids)

        call_command("migrate", "lti_consumer", "0025_copy_lti1p3_passports", verbosity=0)

        new_ct = ContentType.objects.get(**self.NEW_CONTENT_TYPE)
        self.assertEqual(
            set(Permission.objects.filter(content_type=new_ct).values_list("codename", flat=True)),
            {
                "add_reusablelticonfiguration",
                "change_reusablelticonfiguration",
                "delete_reusablelticonfiguration",
                "view_reusablelticonfiguration",
            },
        )
        self.assertEqual(ContentType.objects.get(**self.OLD_CONTENT_TYPE).pk, old_ct.pk)
        self.assertEqual(
            set(Permission.objects.filter(content_type_id=old_ct.pk).values_list("id", flat=True)),
            old_permission_ids,
        )
        self.assertEqual(
            set(Group.objects.get(pk=group.pk).permissions.values_list("id", flat=True)),
            old_permission_ids,
        )
        old_model = django_apps.get_model("lti_consumer", "Lti1p3Passport")
        new_model = django_apps.get_model("lti_consumer", "ReusableLtiConfiguration")
        # The harness orphan and the unplaced duplicate get no copy.
        self.assertEqual(new_model.objects.count(), old_model.objects.count() - 2)
