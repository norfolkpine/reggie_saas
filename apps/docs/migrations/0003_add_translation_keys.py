import uuid

from django.db import migrations, models


def add_translation_keys(apps, schema_editor):
    Page = apps.get_model('wagtailcore.Page')
    for page in Page.objects.all():
        if not page.translation_key:
            page.translation_key = str(uuid.uuid4())
            page.save()

class Migration(migrations.Migration):
    dependencies = [
        ('docs', '0002_initial'),
        ('wagtailcore', '0001_squashed_0016_change_page_url_path_to_text_field'),
    ]

    operations = [
        migrations.RunPython(add_translation_keys),
    ] 