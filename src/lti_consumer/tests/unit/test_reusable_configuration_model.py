"""
Model-level behaviour of the reusable-configuration table.

Signing keys are generated lazily by the accessors, and tool-key settings are validated
in `clean()`; neither promise is enforced by the table schema.
"""

import uuid

from django.core.exceptions import ValidationError
from django.test import TestCase

from lti_consumer.models import ReusableLtiConfiguration


class ReusableConfigurationModelTests(TestCase):
    """Signing-key generation, display and tool-key validation."""

    def make_configuration(self, **kwargs):
        values = {'name': 'Model test', 'version': ReusableLtiConfiguration.LTI_1P3}
        values.update(kwargs)
        return ReusableLtiConfiguration.objects.create(**values)

    def test_private_key_accessor_generates_missing_keys(self):
        configuration = self.make_configuration()

        private_key = configuration.lti_1p3_private_key

        configuration.refresh_from_db()
        self.assertTrue(private_key.startswith('-----BEGIN RSA PRIVATE KEY-----'))
        self.assertEqual(configuration.lti_1p3_internal_private_key, private_key)
        self.assertTrue(configuration.lti_1p3_internal_private_key_id)
        key_set = configuration.lti_1p3_public_jwk['keys']
        self.assertEqual(key_set[0]['kty'], 'RSA')
        self.assertEqual(key_set[0]['kid'], configuration.lti_1p3_internal_private_key_id)

    def test_private_key_id_accessor_generates_missing_keys(self):
        configuration = self.make_configuration()

        key_id = configuration.lti_1p3_private_key_id

        configuration.refresh_from_db()
        self.assertEqual(configuration.lti_1p3_internal_private_key_id, key_id)
        self.assertEqual(uuid.UUID(key_id).version, 4)

    def test_public_jwk_accessor_rebuilds_a_missing_jwk_from_the_stored_private_key(self):
        configuration = self.make_configuration()
        expected_jwk = configuration.lti_1p3_public_jwk
        configuration.lti_1p3_internal_public_jwk = ''
        configuration.save()

        self.assertEqual(configuration.lti_1p3_public_jwk, expected_jwk)
        configuration.refresh_from_db()
        self.assertEqual(configuration.lti_1p3_public_jwk, expected_jwk)

    def test_str_names_the_configuration_and_its_passport(self):
        passport_id = uuid.uuid4()

        configuration = self.make_configuration(passport_id=passport_id)

        self.assertEqual(
            str(configuration),
            f'ReusableLtiConfiguration: Model test - {passport_id}',
        )

    def test_clean_requires_a_public_key_in_public_key_mode(self):
        configuration = self.make_configuration(lti_1p3_tool_key_mode='public_key')

        with self.assertRaisesMessage(ValidationError, 'A public key is required in public-key mode.'):
            configuration.clean()

    def test_clean_requires_a_keyset_url_in_keyset_url_mode(self):
        configuration = self.make_configuration(lti_1p3_tool_key_mode='keyset_url')

        with self.assertRaisesMessage(ValidationError, 'A keyset URL is required in keyset-URL mode.'):
            configuration.clean()

    def test_clean_accepts_absent_and_complete_tool_key_settings(self):
        self.make_configuration().clean()
        self.make_configuration(
            lti_1p3_tool_key_mode='public_key',
            lti_1p3_tool_public_key='-----BEGIN PUBLIC KEY-----',
        ).clean()
        self.make_configuration(
            lti_1p3_tool_key_mode='keyset_url',
            lti_1p3_tool_keyset_url='https://tool.example/jwks',
        ).clean()
