from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reggie', '0013_alter_agent_session_table_alter_agent_unique_code'),
    ]

    operations = [
        migrations.AlterField(
            model_name='agent',
            name='session_table',
            field=models.CharField(
                max_length=255,
                editable=False,
                blank=True,
                unique=True,
                help_text='Table name for session persistence, derived from unique_code.'
            ),
        ),
        migrations.AlterField(
            model_name='agent',
            name='unique_code',
            field=models.CharField(
                max_length=20,
                editable=False,
                unique=True,
                help_text='Unique identifier for the agent, used for session storage.'
            ),
        ),
    ]
