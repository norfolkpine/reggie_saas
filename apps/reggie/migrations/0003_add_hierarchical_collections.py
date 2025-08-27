# Generated manually for hierarchical collections

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("reggie", "0002_initial"),
    ]

    operations = [
        # Add new fields to Collection model
        migrations.AddField(
            model_name="collection",
            name="description",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="collection",
            name="parent",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="children",
                to="reggie.collection",
            ),
        ),
        migrations.AddField(
            model_name="collection",
            name="collection_type",
            field=models.CharField(
                choices=[
                    ("folder", "Folder"),
                    ("regulation", "Regulation"),
                    ("act", "Act"),
                    ("guideline", "Guideline"),
                    ("manual", "Manual"),
                ],
                default="folder",
                max_length=50,
            ),
        ),
        migrations.AddField(
            model_name="collection",
            name="jurisdiction",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="collection",
            name="regulation_number",
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AddField(
            model_name="collection",
            name="effective_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="collection",
            name="sort_order",
            field=models.IntegerField(default=0),
        ),
        # Add new fields to File model
        migrations.AddField(
            model_name="file",
            name="volume_number",
            field=models.IntegerField(blank=True, null=True, help_text="Volume number for multi-volume documents"),
        ),
        migrations.AddField(
            model_name="file",
            name="part_number",
            field=models.CharField(
                blank=True, max_length=20, null=True, help_text="Part or section number (e.g., Part A, Section 1)"
            ),
        ),
        migrations.AddField(
            model_name="file",
            name="collection_order",
            field=models.IntegerField(default=0, help_text="Order of this file within its collection"),
        ),
        # Update Collection model constraints
        migrations.AlterUniqueTogether(
            name="collection",
            unique_together={("name", "parent")},
        ),
        # Update Collection model ordering
        migrations.AlterModelOptions(
            name="collection",
            options={"ordering": ["sort_order", "name"]},
        ),
        # Update File model ordering
        migrations.AlterModelOptions(
            name="file",
            options={"ordering": ["collection", "collection_order", "volume_number", "part_number", "title"]},
        ),
    ]
