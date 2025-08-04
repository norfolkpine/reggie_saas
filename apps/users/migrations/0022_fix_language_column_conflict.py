# Generated manually to fix language column conflict

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0021_merge_20250801_1213'),
    ]

    operations = [
        # This migration ensures the language field exists with the correct structure
        # If the column already exists, this will be a no-op
        migrations.AlterField(
            model_name='customuser',
            name='language',
            field=models.CharField(
                blank=True, 
                choices=[('en', 'English'), ('fr', 'French')], 
                default=None, 
                help_text='The language in which the user wants to see the interface.', 
                max_length=10, 
                null=True, 
                verbose_name='language'
            ),
        ),
    ] 