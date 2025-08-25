"""
Test script for the new hierarchical collection system.
This demonstrates how to create folders and subfolders for organizing regulatory documents.
"""

import os
import sys
import django
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bh_reggie.settings')
django.setup()

from apps.reggie.models import Collection, File
from apps.reggie.serializers import CollectionSerializer, CollectionDetailSerializer

def test_hierarchical_collections():
    """Test the hierarchical collection functionality"""
    
    print("🌳 Testing Hierarchical Collections System")
    print("=" * 50)
    
    # 1. Create root collection for Australian Regulations
    print("\n1. Creating root collection: 'Australian Regulations'")
    root_collection = Collection.objects.create(
        name="Australian Regulations",
        description="Collection of Australian regulatory documents",
        collection_type="folder"
    )
    print(f"   ✅ Created: {root_collection.name} (ID: {root_collection.id})")
    
    # 2. Create subcollection for Corporate Tax Act
    print("\n2. Creating subcollection: 'Corporate Tax Act 2001'")
    tax_act_collection = Collection.objects.create(
        name="Corporate Tax Act 2001",
        description="Australian Corporate Tax Act 2001 with multiple volumes",
        parent=root_collection,
        collection_type="act",
        jurisdiction="Australia",
        regulation_number="2001",
        sort_order=1
    )
    print(f"   ✅ Created: {tax_act_collection.name} (ID: {tax_act_collection.id})")
    print(f"   📁 Parent: {tax_act_collection.parent.name}")
    print(f"   🏛️ Type: {tax_act_collection.collection_type}")
    
    # 3. Create subcollection for AUSTRAC Guidelines
    print("\n3. Creating subcollection: 'AUSTRAC Guidelines'")
    austrac_collection = Collection.objects.create(
        name="AUSTRAC Guidelines",
        description="AUSTRAC anti-money laundering and counter-terrorism financing guidelines",
        parent=root_collection,
        collection_type="guideline",
        jurisdiction="Australia",
        sort_order=2
    )
    print(f"   ✅ Created: {austrac_collection.name} (ID: {austrac_collection.id})")
    
    # 4. Create sub-subcollection for specific AUSTRAC topics
    print("\n4. Creating sub-subcollection: 'AML Guidelines'")
    aml_collection = Collection.objects.create(
        name="AML Guidelines",
        description="Anti-Money Laundering specific guidelines",
        parent=austrac_collection,
        collection_type="guideline",
        sort_order=1
    )
    print(f"   ✅ Created: {aml_collection.name} (ID: {aml_collection.id})")
    print(f"   📁 Parent: {aml_collection.parent.name}")
    print(f"   📂 Full Path: {aml_collection.get_full_path()}")
    
    # 5. Test collection hierarchy methods
    print("\n5. Testing collection hierarchy methods:")
    print(f"   📂 Root collection depth: {root_collection.get_depth()}")
    print(f"   📂 Tax Act depth: {tax_act_collection.get_depth()}")
    print(f"   📂 AML Guidelines depth: {aml_collection.get_depth()}")
    
    print(f"   📂 Tax Act full path: {tax_act_collection.get_full_path()}")
    print(f"   📂 AML Guidelines full path: {aml_collection.get_full_path()}")
    
    # 6. Test getting ancestors and descendants
    print("\n6. Testing ancestor/descendant relationships:")
    aml_ancestors = aml_collection.get_ancestors()
    print(f"   📂 AML Guidelines ancestors: {[c.name for c in aml_ancestors]}")
    
    root_descendants = root_collection.get_descendants()
    print(f"   📂 Root descendants: {[c.name for c in root_descendants]}")
    
    # 7. Test serialization
    print("\n7. Testing serialization:")
    root_serializer = CollectionSerializer(root_collection)
    print(f"   📄 Root collection JSON: {root_serializer.data['name']}")
    print(f"   📄 Root collection children count: {len(root_serializer.data['children'])}")
    
    # 8. Test collection tree
    print("\n8. Testing collection tree structure:")
    def print_tree(collection, level=0):
        indent = "  " * level
        print(f"{indent}📁 {collection.name} ({collection.collection_type})")
        for child in collection.children.all().order_by('sort_order', 'name'):
            print_tree(child, level + 1)
    
    print_tree(root_collection)
    
    print("\n" + "=" * 50)
    print("✅ Hierarchical Collections Test Completed Successfully!")
    
    # Clean up test data
    print("\n🧹 Cleaning up test data...")
    root_collection.delete()
    print("   ✅ Test data cleaned up")

if __name__ == "__main__":
    try:
        test_hierarchical_collections()
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
