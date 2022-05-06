# Generated by Django 3.2.13 on 2022-06-02 20:14

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lti_consumer', '0014_adds_external_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='lticonfiguration',
            name='lti_1p3_launch_url',
            field=models.CharField(blank=True, help_text='This is the LTI launch URL, otherwise known as the target_link_uri.It represents the LTI resource to launch to in the second leg of the launch flow, when the resource is actually launched.', max_length=255),
        ),
        migrations.AddField(
            model_name='lticonfiguration',
            name='lti_1p3_oidc_url',
            field=models.CharField(blank=True, help_text='This is the OIDC login intitiation URL in the LTI 1.3 flow, which should be provided by the LTI Tool.', max_length=255),
        ),
        migrations.AddField(
            model_name='lticonfiguration',
            name='lti_1p3_tool_keyset_url',
            field=models.CharField(blank=True, help_text="This is the Tool's JWK (JSON Web Key) keyset URL. This should be provided by the LTI Tool. One of either lti_1p3_tool_public_key or lti_1p3_tool_keyset_url must not be blank.", max_length=255),
        ),
        migrations.AddField(
            model_name='lticonfiguration',
            name='lti_1p3_tool_public_key',
            field=models.TextField(blank=True, help_text="This is the Tool's public key. This should be provided by the LTI Tool. One of either lti_1p3_tool_public_key or lti_1p3_tool_keyset_url must not be blank."),
        ),
    ]
