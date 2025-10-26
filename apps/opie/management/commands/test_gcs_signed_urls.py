from django.core.management.base import BaseCommand
from django.core.files.storage import default_storage
import os

class Command(BaseCommand):
    help = 'Test GCS signed URL generation'

    def add_arguments(self, parser):
        parser.add_argument(
            '--test-file',
            type=str,
            default='test-signed-url.txt',
            help='Test file name to use for signed URL generation'
        )

    def handle(self, *args, **options):
        test_file = options['test_file']
        
        self.stdout.write("🧪 Testing GCS Signed URL Generation...")
        
        # Test 1: Create a test file
        from django.core.files.base import ContentFile
        test_content = "Test content for GCS signed URL generation"
        try:
            default_storage.save(test_file, ContentFile(test_content.encode('utf-8')))
            self.stdout.write(self.style.SUCCESS(f"✅ Test file created: {test_file}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Failed to create test file: {e}"))
            return
        
        # Test 2: Generate signed URL
        try:
            signed_url = default_storage.url(test_file)
            self.stdout.write(self.style.SUCCESS(f"✅ Signed URL generated successfully"))
            self.stdout.write(f"URL: {signed_url}")
            
            # Check if it's a signed URL (contains signature parameters)
            if 'X-Goog-Signature' in signed_url or 'X-Goog-Algorithm' in signed_url:
                self.stdout.write(self.style.SUCCESS("✅ URL appears to be properly signed"))
            else:
                self.stdout.write(self.style.WARNING("⚠️  URL may not be signed (could be public URL)"))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Failed to generate signed URL: {e}"))
            return
        
        # Test 3: Clean up
        try:
            default_storage.delete(test_file)
            self.stdout.write(self.style.SUCCESS("✅ Test file cleaned up"))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"⚠️  Failed to clean up test file: {e}"))
        
        # Test 4: Show current GCS configuration
        self.stdout.write("\n📋 Current GCS Configuration:")
        from django.conf import settings
        storages = getattr(settings, 'STORAGES', {})
        if 'default' in storages:
            default_storage_config = storages['default']
            self.stdout.write(f"Backend: {default_storage_config.get('BACKEND', 'Not set')}")
            
            if 'OPTIONS' in default_storage_config:
                options = default_storage_config['OPTIONS']
                self.stdout.write(f"Bucket: {options.get('bucket_name', 'Not set')}")
                self.stdout.write(f"File overwrite: {options.get('file_overwrite', 'Not set')}")
                self.stdout.write(f"Default ACL: {options.get('default_acl', 'Not set')}")
                
                if 'credentials' in options:
                    creds = options['credentials']
                    self.stdout.write(f"Credentials type: {type(creds).__name__}")
                    
                    # Check if credentials support signing
                    if hasattr(creds, 'sign'):
                        self.stdout.write("✅ Credentials support signing")
                    else:
                        self.stdout.write("❌ Credentials do NOT support signing")
        
        self.stdout.write(self.style.SUCCESS("\n🏁 GCS Signed URL Test Complete!"))
