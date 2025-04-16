from django.db import migrations, models
import django.db.models.deletion

def migrate_app_data(apps, schema_editor):
    ConnectedApp = apps.get_model('app_integrations', 'ConnectedApp')
    SupportedApp = apps.get_model('app_integrations', 'SupportedApp')
    
    for connected_app in ConnectedApp.objects.all():
        try:
            supported_app = SupportedApp.objects.get(key=connected_app.app)
            connected_app.app_id = supported_app.id
            connected_app.save()
        except SupportedApp.DoesNotExist:
            connected_app.delete()

class Migration(migrations.Migration):
    dependencies = [
        ('app_integrations', '0004_merge_20250414_0413'),
    ]

    operations = [
        migrations.RenameField(
            model_name='connectedapp',
            old_name='app',
            new_name='app_key',
        ),
        migrations.AddField(
            model_name='connectedapp',
            name='app',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='connected_apps', to='app_integrations.supportedapp'),
        ),
        migrations.RunPython(migrate_app_data),
        migrations.RemoveField(
            model_name='connectedapp',
            name='app_key',
        ),
        migrations.AlterField(
            model_name='connectedapp',
            name='app',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='connected_apps', to='app_integrations.supportedapp'),
        ),
    ]