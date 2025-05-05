from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reggie', '0003_file_metadata_and_progress'),
    ]

    operations = [
        migrations.AddField(
            model_name='knowledgebase',
            name='chunk_size',
            field=models.IntegerField(default=1000, help_text='Size of chunks used for text splitting during ingestion.'),
        ),
        migrations.AddField(
            model_name='knowledgebase',
            name='chunk_overlap',
            field=models.IntegerField(default=200, help_text='Number of characters to overlap between chunks.'),
        ),
    ] 