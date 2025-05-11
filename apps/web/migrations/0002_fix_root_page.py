from django.db import migrations

def create_root_page(apps, schema_editor):
    Page = apps.get_model('wagtailcore', 'Page')
    ContentType = apps.get_model('contenttypes', 'ContentType')
    
    # Get the page content type
    page_content_type = ContentType.objects.get_for_model(Page)
    
    # Create the root page if it doesn't exist
    if not Page.objects.filter(id=1).exists():
        root_page = Page.objects.create(
            id=1,
            title="Root",
            draft_title="Root",  # Set draft_title to match title
            slug='root',
            content_type=page_content_type,
            path='0001',
            depth=1,
            numchild=0,
            url_path='/',
            show_in_menus=True,
            live=True,
            has_unpublished_changes=False,
        )

def remove_root_page(apps, schema_editor):
    Page = apps.get_model('wagtailcore', 'Page')
    Page.objects.filter(id=1).delete()

class Migration(migrations.Migration):
    dependencies = [
        ('wagtailcore', '0001_squashed_0016_change_page_url_path_to_text_field'),
        ('web', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_root_page, remove_root_page),
    ] 