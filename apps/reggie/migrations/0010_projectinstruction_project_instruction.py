# Generated manually for adding ProjectInstruction model

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('reggie', '0009_project_vault_vector_table_vaultfile_embedded_at_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProjectInstruction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(help_text='Name of this instruction template', max_length=255)),
                ('content', models.TextField(help_text='The instruction/prompt content for AI processing')),
                ('description', models.TextField(blank=True, help_text='Description of what this instruction does', null=True)),
                ('is_active', models.BooleanField(default=True, help_text='Whether this instruction is currently active')),
                ('instruction_type', models.CharField(
                    choices=[
                        ('vault_chat', 'Vault Chat'),
                        ('file_insight', 'File Insight Generation'),
                        ('summary', 'Document Summary'),
                        ('extraction', 'Data Extraction'),
                        ('custom', 'Custom')
                    ],
                    default='vault_chat',
                    help_text='Type of instruction for different use cases',
                    max_length=50
                )),
                ('created_by', models.ForeignKey(
                    help_text='User who created this instruction',
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='created_project_instructions',
                    to=settings.AUTH_USER_MODEL
                )),
            ],
            options={
                'verbose_name': 'Project Instruction',
                'verbose_name_plural': 'Project Instructions',
                'ordering': ['-created_at'],
                'indexes': [
                    models.Index(fields=['instruction_type', 'is_active'], name='reggie_proj_instruc_9f8d2a_idx'),
                    models.Index(fields=['created_by'], name='reggie_proj_created_2b4e1c_idx'),
                ],
            },
        ),
        migrations.AddField(
            model_name='project',
            name='instruction',
            field=models.ForeignKey(
                blank=True,
                help_text="Custom instruction template for this project's AI operations",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='projects',
                to='reggie.projectinstruction'
            ),
        ),
    ]