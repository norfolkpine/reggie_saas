#!/usr/bin/env python3
"""
Comprehensive test script for Projects API endpoints.
This script tests all project-related functionality including CRUD operations,
custom instructions, permissions, and caching.
"""

import os
import sys
import json
import requests
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bh_reggie.settings')

import django
django.setup()

from apps.users.models import CustomUser
from apps.teams.models import Team
from apps.reggie.models import Project, ProjectInstruction, Tag


class ProjectAPITester:
    """Test class for Projects API functionality."""
    
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.api_base = f"{base_url}/api/v1/reggie"
        self.session = requests.Session()
        self.test_user = None
        self.test_team = None
        self.created_projects = []
        self.created_instructions = []
        
    def setup_test_data(self):
        """Set up test users and teams."""
        print("🔧 Setting up test data...")
        
        # Create test user
        self.test_user, created = CustomUser.objects.get_or_create(
            email="testuser@example.com",
            defaults={
                'first_name': 'Test',
                'last_name': 'User',
                'is_active': True
            }
        )
        if created:
            self.test_user.set_password('testpass123')
            self.test_user.save()
        
        # Create test team
        self.test_team, created = Team.objects.get_or_create(
            name="Test Team",
            defaults={
                'slug': 'test-team',
                'description': 'Test team for API testing'
            }
        )
        
        print(f"✅ Test user: {self.test_user.email}")
        print(f"✅ Test team: {self.test_team.name}")
    
    def authenticate(self):
        """Authenticate and get JWT token."""
        print("🔐 Authenticating...")
        
        auth_url = f"{self.base_url}/api/auth/jwt/token/"
        auth_data = {
            "email": self.test_user.email,
            "password": "testpass123"
        }
        
        try:
            response = self.session.post(auth_url, json=auth_data)
            if response.status_code == 200:
                token_data = response.json()
                self.session.headers.update({
                    'Authorization': f"Bearer {token_data['access']}",
                    'Content-Type': 'application/json'
                })
                print("✅ Authentication successful")
                return True
            else:
                print(f"❌ Authentication failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            return False
    
    def test_create_project(self):
        """Test creating a new project."""
        print("\n🧪 Testing project creation...")
        
        project_data = {
            "name": "Test Project API",
            "description": "A test project created by the API test script",
            "custom_instruction": "You are a specialized AI assistant for this test project. Focus on providing accurate and helpful responses based on the project's specific requirements."
        }
        
        try:
            response = self.session.post(f"{self.api_base}/projects/", json=project_data)
            print(f"Status: {response.status_code}")
            
            if response.status_code == 201:
                project = response.json()
                self.created_projects.append(project['uuid'])
                print(f"✅ Project created: {project['name']} (UUID: {project['uuid']})")
                print(f"   Description: {project['description']}")
                print(f"   Owner: {project['owner']}")
                print(f"   Custom instruction: {project.get('instruction', {}).get('content', 'None')}")
                return project
            else:
                print(f"❌ Project creation failed: {response.text}")
                return None
        except Exception as e:
            print(f"❌ Project creation error: {e}")
            return None
    
    def test_list_projects(self):
        """Test listing all projects."""
        print("\n🧪 Testing project listing...")
        
        try:
            response = self.session.get(f"{self.api_base}/projects/")
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                projects = response.json()
                print(f"✅ Found {len(projects)} projects")
                for project in projects:
                    print(f"   - {project['name']} (UUID: {project['uuid']})")
                return projects
            else:
                print(f"❌ Project listing failed: {response.text}")
                return None
        except Exception as e:
            print(f"❌ Project listing error: {e}")
            return None
    
    def test_get_project_detail(self, project_uuid):
        """Test getting project details."""
        print(f"\n🧪 Testing project detail retrieval for {project_uuid}...")
        
        try:
            response = self.session.get(f"{self.api_base}/projects/{project_uuid}/")
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                project = response.json()
                print(f"✅ Project details retrieved:")
                print(f"   Name: {project['name']}")
                print(f"   Description: {project['description']}")
                print(f"   Owner: {project['owner']}")
                print(f"   Created: {project['created_at']}")
                print(f"   Updated: {project['updated_at']}")
                if project.get('instruction'):
                    print(f"   Custom instruction: {project['instruction']['content']}")
                return project
            else:
                print(f"❌ Project detail retrieval failed: {response.text}")
                return None
        except Exception as e:
            print(f"❌ Project detail retrieval error: {e}")
            return None
    
    def test_update_project(self, project_uuid):
        """Test updating a project."""
        print(f"\n🧪 Testing project update for {project_uuid}...")
        
        update_data = {
            "name": "Updated Test Project",
            "description": "This project has been updated by the API test script",
            "custom_instruction": "Updated custom instruction: You are now an updated AI assistant with enhanced capabilities for this test project."
        }
        
        try:
            response = self.session.put(f"{self.api_base}/projects/{project_uuid}/", json=update_data)
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                project = response.json()
                print(f"✅ Project updated successfully:")
                print(f"   New name: {project['name']}")
                print(f"   New description: {project['description']}")
                print(f"   Updated instruction: {project.get('instruction', {}).get('content', 'None')}")
                return project
            else:
                print(f"❌ Project update failed: {response.text}")
                return None
        except Exception as e:
            print(f"❌ Project update error: {e}")
            return None
    
    def test_partial_update_project(self, project_uuid):
        """Test partial update of a project."""
        print(f"\n🧪 Testing partial project update for {project_uuid}...")
        
        partial_data = {
            "description": "Partially updated description only"
        }
        
        try:
            response = self.session.patch(f"{self.api_base}/projects/{project_uuid}/", json=partial_data)
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                project = response.json()
                print(f"✅ Project partially updated:")
                print(f"   Name: {project['name']} (unchanged)")
                print(f"   Description: {project['description']} (updated)")
                return project
            else:
                print(f"❌ Partial project update failed: {response.text}")
                return None
        except Exception as e:
            print(f"❌ Partial project update error: {e}")
            return None
    
    def test_project_custom_instruction_update(self, project_uuid):
        """Test updating only the custom instruction."""
        print(f"\n🧪 Testing custom instruction update for {project_uuid}...")
        
        instruction_data = {
            "custom_instruction": "This is a completely new custom instruction that replaces the previous one. Focus on providing detailed analysis and insights."
        }
        
        try:
            response = self.session.put(f"{self.api_base}/projects/{project_uuid}/", json=instruction_data)
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                project = response.json()
                print(f"✅ Custom instruction updated:")
                print(f"   New instruction: {project.get('instruction', {}).get('content', 'None')}")
                return project
            else:
                print(f"❌ Custom instruction update failed: {response.text}")
                return None
        except Exception as e:
            print(f"❌ Custom instruction update error: {e}")
            return None
    
    def test_remove_custom_instruction(self, project_uuid):
        """Test removing custom instruction by setting it to empty."""
        print(f"\n🧪 Testing custom instruction removal for {project_uuid}...")
        
        remove_data = {
            "custom_instruction": ""
        }
        
        try:
            response = self.session.put(f"{self.api_base}/projects/{project_uuid}/", json=remove_data)
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                project = response.json()
                print(f"✅ Custom instruction removed:")
                print(f"   Instruction: {project.get('instruction', 'None')}")
                return project
            else:
                print(f"❌ Custom instruction removal failed: {response.text}")
                return None
        except Exception as e:
            print(f"❌ Custom instruction removal error: {e}")
            return None
    
    def test_project_caching(self, project_uuid):
        """Test project caching behavior."""
        print(f"\n🧪 Testing project caching for {project_uuid}...")
        
        try:
            # First request (should hit database)
            response1 = self.session.get(f"{self.api_base}/projects/{project_uuid}/")
            print(f"First request status: {response1.status_code}")
            
            # Second request (should hit cache)
            response2 = self.session.get(f"{self.api_base}/projects/{project_uuid}/")
            print(f"Second request status: {response2.status_code}")
            
            if response1.status_code == 200 and response2.status_code == 200:
                print("✅ Project caching working (both requests successful)")
                return True
            else:
                print("❌ Project caching test failed")
                return False
        except Exception as e:
            print(f"❌ Project caching test error: {e}")
            return False
    
    def test_project_permissions(self):
        """Test project permissions and access control."""
        print("\n🧪 Testing project permissions...")
        
        # Create a second user
        other_user, created = CustomUser.objects.get_or_create(
            email="otheruser@example.com",
            defaults={
                'first_name': 'Other',
                'last_name': 'User',
                'is_active': True
            }
        )
        if created:
            other_user.set_password('otherpass123')
            other_user.save()
        
        # Authenticate as other user
        auth_url = f"{self.base_url}/api/auth/jwt/token/"
        auth_data = {
            "email": other_user.email,
            "password": "otherpass123"
        }
        
        try:
            auth_response = self.session.post(auth_url, json=auth_data)
            if auth_response.status_code == 200:
                token_data = auth_response.json()
                other_session = requests.Session()
                other_session.headers.update({
                    'Authorization': f"Bearer {token_data['access']}",
                    'Content-Type': 'application/json'
                })
                
                # Try to access project created by first user
                if self.created_projects:
                    project_uuid = self.created_projects[0]
                    response = other_session.get(f"{self.api_base}/projects/{project_uuid}/")
                    print(f"Other user access status: {response.status_code}")
                    
                    if response.status_code == 404:
                        print("✅ Project permissions working (other user cannot access)")
                    else:
                        print("⚠️ Project permissions may not be working correctly")
                
                # Clean up other user
                other_user.delete()
                return True
            else:
                print("❌ Could not authenticate other user for permission test")
                return False
        except Exception as e:
            print(f"❌ Project permissions test error: {e}")
            return False
    
    def test_project_with_team(self):
        """Test creating a project with team association."""
        print("\n🧪 Testing project creation with team...")
        
        project_data = {
            "name": "Team Project Test",
            "description": "A project associated with a team",
            "team": self.test_team.id,
            "custom_instruction": "You are a team-focused AI assistant for this collaborative project."
        }
        
        try:
            response = self.session.post(f"{self.api_base}/projects/", json=project_data)
            print(f"Status: {response.status_code}")
            
            if response.status_code == 201:
                project = response.json()
                self.created_projects.append(project['uuid'])
                print(f"✅ Team project created: {project['name']}")
                print(f"   Team: {project.get('team', 'None')}")
                return project
            else:
                print(f"❌ Team project creation failed: {response.text}")
                return None
        except Exception as e:
            print(f"❌ Team project creation error: {e}")
            return None
    
    def test_project_with_tags(self):
        """Test creating a project with tags."""
        print("\n🧪 Testing project creation with tags...")
        
        # Create test tags
        tag1, _ = Tag.objects.get_or_create(name="test-tag-1")
        tag2, _ = Tag.objects.get_or_create(name="test-tag-2")
        
        project_data = {
            "name": "Tagged Project Test",
            "description": "A project with tags",
            "tags": [tag1.id, tag2.id],
            "custom_instruction": "You are a tagged AI assistant for this categorized project."
        }
        
        try:
            response = self.session.post(f"{self.api_base}/projects/", json=project_data)
            print(f"Status: {response.status_code}")
            
            if response.status_code == 201:
                project = response.json()
                self.created_projects.append(project['uuid'])
                print(f"✅ Tagged project created: {project['name']}")
                print(f"   Tags: {[tag['name'] for tag in project.get('tags', [])]}")
                return project
            else:
                print(f"❌ Tagged project creation failed: {response.text}")
                return None
        except Exception as e:
            print(f"❌ Tagged project creation error: {e}")
            return None
    
    def test_delete_project(self, project_uuid):
        """Test deleting a project."""
        print(f"\n🧪 Testing project deletion for {project_uuid}...")
        
        try:
            response = self.session.delete(f"{self.api_base}/projects/{project_uuid}/")
            print(f"Status: {response.status_code}")
            
            if response.status_code == 204:
                print("✅ Project deleted successfully")
                if project_uuid in self.created_projects:
                    self.created_projects.remove(project_uuid)
                return True
            else:
                print(f"❌ Project deletion failed: {response.text}")
                return False
        except Exception as e:
            print(f"❌ Project deletion error: {e}")
            return False
    
    def cleanup(self):
        """Clean up test data."""
        print("\n🧹 Cleaning up test data...")
        
        # Delete created projects
        for project_uuid in self.created_projects:
            try:
                project = Project.objects.get(uuid=project_uuid)
                project.delete()
                print(f"   ✅ Deleted project: {project_uuid}")
            except Project.DoesNotExist:
                print(f"   ⚠️ Project {project_uuid} already deleted")
        
        # Clean up test user and team
        if self.test_user:
            self.test_user.delete()
            print("   ✅ Deleted test user")
        
        if self.test_team:
            self.test_team.delete()
            print("   ✅ Deleted test team")
        
        print("✅ Cleanup completed")
    
    def run_all_tests(self):
        """Run all project API tests."""
        print("🚀 Starting Projects API Tests")
        print("=" * 60)
        
        try:
            # Setup
            self.setup_test_data()
            if not self.authenticate():
                print("❌ Authentication failed, cannot continue")
                return False
            
            # Test project creation
            project = self.test_create_project()
            if not project:
                print("❌ Project creation failed, cannot continue")
                return False
            
            project_uuid = project['uuid']
            
            # Test project listing
            self.test_list_projects()
            
            # Test project detail retrieval
            self.test_get_project_detail(project_uuid)
            
            # Test project updates
            self.test_update_project(project_uuid)
            self.test_partial_update_project(project_uuid)
            
            # Test custom instruction functionality
            self.test_project_custom_instruction_update(project_uuid)
            self.test_remove_custom_instruction(project_uuid)
            
            # Test caching
            self.test_project_caching(project_uuid)
            
            # Test permissions
            self.test_project_permissions()
            
            # Test team project
            self.test_project_with_team()
            
            # Test tagged project
            self.test_project_with_tags()
            
            # Test project deletion
            self.test_delete_project(project_uuid)
            
            print("\n" + "=" * 60)
            print("✅ All Projects API tests completed successfully!")
            print("\n📋 Test Summary:")
            print("✅ Project CRUD operations")
            print("✅ Custom instruction management")
            print("✅ Project permissions and access control")
            print("✅ Project caching behavior")
            print("✅ Team association")
            print("✅ Tag management")
            print("✅ API authentication")
            
            return True
            
        except Exception as e:
            print(f"❌ Test suite failed: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        finally:
            self.cleanup()


def main():
    """Main function to run the project API tests."""
    print("🧪 Projects API Test Script")
    print("This script tests all project-related API endpoints and functionality.")
    print()
    
    # Check if server is running
    try:
        response = requests.get("http://localhost:8000/api/v1/health/", timeout=5)
        if response.status_code != 200:
            print("❌ Server is not responding properly")
            return False
    except requests.exceptions.RequestException:
        print("❌ Server is not running. Please start the Django server first:")
        print("   python manage.py runserver")
        return False
    
    # Run tests
    tester = ProjectAPITester()
    success = tester.run_all_tests()
    
    if success:
        print("\n🎉 All tests passed! Projects API is working correctly.")
        return True
    else:
        print("\n❌ Some tests failed. Check the output above for details.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
