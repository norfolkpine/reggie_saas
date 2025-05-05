from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reggie', '0002_alter_storagebucket_team'),
    ]

    operations = [
        migrations.AddField(
            model_name='file',
            name='total_documents',
            field=models.IntegerField(
                default=0,
                help_text='Total number of documents extracted from this file'
            ),
        ),
        migrations.AddField(
            model_name='file',
            name='page_count',
            field=models.IntegerField(
                default=0,
                help_text='Number of pages in the document (for PDFs)'
            ),
        ),
        migrations.AddField(
            model_name='file',
            name='file_size',
            field=models.BigIntegerField(
                default=0,
                help_text='Size of the file in bytes'
            ),
        ),
        migrations.AddField(
            model_name='fileknowledgebaselink',
            name='embedding_model',
            field=models.CharField(blank=True, help_text='Model used for embeddings (e.g. text-embedding-ada-002)', max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='fileknowledgebaselink',
            name='chunk_size',
            field=models.IntegerField(default=0, help_text='Size of chunks used for processing'),
        ),
        migrations.AddField(
            model_name='fileknowledgebaselink',
            name='chunk_overlap',
            field=models.IntegerField(default=0, help_text='Overlap between chunks'),
        ),
    ] 