from django.db import migrations

def create_initial_apps(apps, schema_editor):
    SupportedApp = apps.get_model('app_integrations', 'SupportedApp')
    initial_apps = [
        {
            'key': 'google_drive',
            'title': 'Google Drive',
            'description': 'Connect with Google Drive to manage your files and documents.',
            'icon_url': 'https://upload.wikimedia.org/wikipedia/commons/1/12/Google_Drive_icon_(2020).svg'
        },
        {
            'key': 'jira',
            'title': 'Jira',
            'description': 'Integrate with Jira for project and issue tracking.',
            'icon_url': 'https://upload.wikimedia.org/wikipedia/commons/8/82/Jira_(Software)_logo.svg'
        },
        {
            'key': 'confluence',
            'title': 'Confluence',
            'description': 'Connect with Confluence for team collaboration and documentation.',
            'icon_url': 'https://upload.wikimedia.org/wikipedia/commons/8/88/Confluence_2017_icon.svg'
        },
    ]
    
    for app_data in initial_apps:
        SupportedApp.objects.create(**app_data)

def delete_initial_apps(apps, schema_editor):
    SupportedApp = apps.get_model('app_integrations', 'SupportedApp')
    SupportedApp.objects.all().delete()

class Migration(migrations.Migration):
    dependencies = [
        ('app_integrations', '0002_supportedapp'),
    ]

    operations = [
        migrations.RunPython(create_initial_apps, delete_initial_apps),
    ]