from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reggie', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='storagebucket',
            name='team',
            field=models.ForeignKey(
                blank=True,
                help_text='Optional team. System buckets have no team.',
                null=True,
                on_delete=models.CASCADE,
                to='teams.team',
                verbose_name='Team'
            ),
        ),
    ] 