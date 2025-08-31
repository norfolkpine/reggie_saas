# Generated manually for Nango integration

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app_integrations', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='connectedapp',
            name='nango_connection_id',
            field=models.CharField(blank=True, db_index=True, help_text='Nango connection ID for this integration', max_length=255),
        ),
        migrations.AddField(
            model_name='connectedapp',
            name='use_nango',
            field=models.BooleanField(default=True, help_text='Whether to use Nango for this connection'),
        ),
        migrations.AlterField(
            model_name='connectedapp',
            name='access_token',
            field=models.CharField(blank=True, max_length=512),
        ),
    ]