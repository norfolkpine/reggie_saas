from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('app_integrations', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='SupportedApp',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(max_length=50, unique=True)),
                ('title', models.CharField(max_length=100)),
                ('description', models.TextField(blank=True)),
                ('icon_url', models.URLField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['title'],
            },
        ),
    ]