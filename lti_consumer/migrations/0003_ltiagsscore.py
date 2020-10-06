# Generated by Django 2.2.16 on 2020-10-01 17:33

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('lti_consumer', '0002_ltiagslineitem'),
    ]

    operations = [
        migrations.CreateModel(
            name='LtiAgsScore',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('timestamp', models.DateTimeField()),
                ('score_given', models.FloatField()),
                ('score_maximum', models.FloatField()),
                ('comment', models.TextField()),
                ('activity_progress', models.CharField(choices=[('initialized', 'Initialized'), ('started', 'Started'), ('in_progress', 'InProgress'), ('submitted', 'Submitted'), ('completed', 'Completed')], max_length=20)),
                ('grading_progress', models.CharField(choices=[('fully_graded', 'FullyGraded'), ('pending', 'Pending'), ('pending_manual', 'PendingManual'), ('failed', 'Failed'), ('not_ready', 'NotReady')], max_length=20)),
                ('user_id', models.CharField(max_length=255)),
                ('line_item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='scores', to='lti_consumer.LtiAgsLineItem')),
            ],
        ),
    ]
