from django.db import migrations, models
import uuid

def gen_uuid(apps, schema_editor):
    File = apps.get_model('reggie', 'File')
    for row in File.objects.all():
        row.uuid = uuid.uuid4()
        row.save(update_fields=['uuid'])

class Migration(migrations.Migration):
    dependencies = [
        ('reggie', '0004_knowledgebase_chunk_settings'),
    ]

    operations = [
        migrations.AddField(
            model_name='file',
            name='uuid',
            field=models.UUIDField(null=True),
        ),
        migrations.RunPython(gen_uuid, reverse_code=migrations.RunPython.noop),
        migrations.AlterField(
            model_name='file',
            name='uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ] 