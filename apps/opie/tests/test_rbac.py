"""
Tests for RBAC (Role-Based Access Control) functionality in the vector database.

This test suite validates that users can only access vectors and knowledge bases
they have permission to see, ensuring proper data isolation in the RAG system.
"""

import uuid
from unittest.mock import Mock, patch

from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.teams.models import Team, Membership
from apps.opie.models import KnowledgeBase, KnowledgeBasePermission
from apps.opie.services.rbac_service import RBACService
from apps.opie.agents.helpers.retrievers import RBACFilteredRetriever

User = get_user_model()


class RBACServiceTest(TestCase):
    """Test the RBAC service functionality."""
    
    def setUp(self):
        """Set up test data."""
        # Create users
        self.user1 = User.objects.create_user(
            email='user1@test.com',
            username='user1',
            password='testpass123'
        )
        self.user2 = User.objects.create_user(
            email='user2@test.com', 
            username='user2',
            password='testpass123'
        )
        self.user3 = User.objects.create_user(
            email='user3@test.com',
            username='user3', 
            password='testpass123'
        )
        
        # Create teams
        self.team1 = Team.objects.create(name="Team 1", slug="team-1")
        self.team2 = Team.objects.create(name="Team 2", slug="team-2")
        
        # Create memberships
        Membership.objects.create(user=self.user1, team=self.team1, role="admin")
        Membership.objects.create(user=self.user2, team=self.team1, role="member")
        Membership.objects.create(user=self.user3, team=self.team2, role="admin")
        
        # Create knowledge bases
        self.kb1 = KnowledgeBase.objects.create(
            name="KB 1",
            knowledgebase_id="kb1-test",
            uploaded_by=self.user1
        )
        self.kb2 = KnowledgeBase.objects.create(
            name="KB 2", 
            knowledgebase_id="kb2-test",
            uploaded_by=self.user2
        )
        
        # Create permissions
        KnowledgeBasePermission.objects.create(
            knowledge_base=self.kb1,
            team=self.team1,
            role=KnowledgeBasePermission.ROLE_VIEWER
        )
    
    def test_get_user_accessible_filters_own_documents(self):
        """Test that users can access their own documents."""
        filters = RBACService.get_user_accessible_filters(self.user1)
        
        # Should include user's own UUID
        self.assertIn("$or", filters)
        user_filter = None
        for condition in filters["$or"]:
            if "user_uuid" in condition:
                user_filter = condition
                break
        
        self.assertIsNotNone(user_filter)
        self.assertEqual(user_filter["user_uuid"], str(self.user1.uuid))
    
    def test_get_user_accessible_filters_team_documents(self):
        """Test that users can access team documents."""
        filters = RBACService.get_user_accessible_filters(self.user1)
        
        # Should include team access
        self.assertIn("$or", filters)
        team_filter = None
        for condition in filters["$or"]:
            if "team_id" in condition:
                team_filter = condition
                break
        
        self.assertIsNotNone(team_filter)
        self.assertIn(str(self.team1.id), team_filter["team_id"]["$in"])
    
    def test_get_user_accessible_filters_knowledge_base(self):
        """Test that users can access permitted knowledge bases."""
        filters = RBACService.get_user_accessible_filters(self.user1)
        
        # Should include knowledge base access
        self.assertIn("$or", filters)
        kb_filter = None
        for condition in filters["$or"]:
            if "knowledgebase_id" in condition:
                kb_filter = condition
                break
        
        self.assertIsNotNone(kb_filter)
        self.assertIn("kb1-test", kb_filter["knowledgebase_id"]["$in"])
    
    def test_can_user_access_knowledge_base_owner(self):
        """Test that knowledge base owner can access it."""
        can_access = RBACService.can_user_access_knowledge_base(self.user1, "kb1-test")
        self.assertTrue(can_access)
    
    def test_can_user_access_knowledge_base_team_permission(self):
        """Test that team members can access KB through permissions."""
        can_access = RBACService.can_user_access_knowledge_base(self.user2, "kb1-test")
        self.assertTrue(can_access)
    
    def test_can_user_access_knowledge_base_denied(self):
        """Test that users without permission cannot access KB."""
        can_access = RBACService.can_user_access_knowledge_base(self.user3, "kb1-test")
        self.assertFalse(can_access)
    
    def test_get_permission_level_owner(self):
        """Test that owner gets owner permission level."""
        level = RBACService.get_permission_level(self.user1, "kb1-test")
        self.assertEqual(level, KnowledgeBasePermission.ROLE_OWNER)
    
    def test_get_permission_level_team_member(self):
        """Test that team member gets assigned permission level."""
        level = RBACService.get_permission_level(self.user2, "kb1-test")
        self.assertEqual(level, KnowledgeBasePermission.ROLE_VIEWER)
    
    def test_get_permission_level_no_access(self):
        """Test that user without access gets None."""
        level = RBACService.get_permission_level(self.user3, "kb1-test")
        self.assertIsNone(level)
    
    def test_validate_ingestion_metadata_valid_team(self):
        """Test validation of ingestion metadata with valid team."""
        metadata = {
            'team_id': str(self.team1.id),
            'knowledgebase_id': 'kb1-test'
        }
        
        errors = RBACService.validate_ingestion_metadata(self.user1, metadata)
        self.assertEqual(errors, {})
    
    def test_validate_ingestion_metadata_invalid_team(self):
        """Test validation of ingestion metadata with invalid team."""
        metadata = {
            'team_id': str(self.team2.id),  # User1 not in team2
            'knowledgebase_id': 'kb1-test'
        }
        
        errors = RBACService.validate_ingestion_metadata(self.user1, metadata)
        self.assertIn('team_id', errors)
    
    def test_validate_ingestion_metadata_invalid_kb(self):
        """Test validation of ingestion metadata with invalid KB."""
        metadata = {
            'knowledgebase_id': 'kb2-test'  # User1 doesn't have access to kb2
        }
        
        errors = RBACService.validate_ingestion_metadata(self.user1, metadata)
        self.assertIn('knowledgebase_id', errors)


class RBACFilteredRetrieverTest(TestCase):
    """Test the RBAC filtered retriever."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@test.com',
            username='testuser',
            password='testpass123'
        )
        
        # Mock base retriever
        self.base_retriever = Mock()
        self.base_retriever.retrieve.return_value = []
    
    def test_rbac_filtered_retriever_initialization(self):
        """Test that RBAC filtered retriever initializes correctly."""
        with patch('apps.opie.services.rbac_service.RBACService.get_user_accessible_filters') as mock_filters:
            mock_filters.return_value = {"user_uuid": str(self.user.uuid)}
            
            retriever = RBACFilteredRetriever(self.base_retriever, self.user)
            
            self.assertEqual(retriever.user, self.user)
            self.assertEqual(retriever.filters, {"user_uuid": str(self.user.uuid)})
    
    def test_rbac_filtered_retriever_no_access(self):
        """Test that retriever returns empty results when user has no access."""
        retriever = RBACFilteredRetriever(self.base_retriever, self.user, filters={})
        
        results = retriever._retrieve("test query")
        
        self.assertEqual(results, [])
    
    def test_rbac_filtered_retriever_with_filters(self):
        """Test retrieval with RBAC filters applied."""
        # Mock node with metadata
        mock_node = Mock()
        mock_node.metadata = {"user_uuid": str(self.user.uuid), "team_id": "123"}
        
        self.base_retriever.retrieve.return_value = [mock_node]
        
        filters = {"user_uuid": str(self.user.uuid)}
        retriever = RBACFilteredRetriever(self.base_retriever, self.user, filters=filters)
        
        results = retriever._retrieve("test query")
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], mock_node)
    
    def test_node_matches_filters_single_condition(self):
        """Test node matching with single filter condition."""
        filters = {"user_uuid": "user123"}
        retriever = RBACFilteredRetriever(self.base_retriever, self.user, filters=filters)
        
        # Matching node
        matching_node = Mock()
        matching_node.metadata = {"user_uuid": "user123", "other_field": "value"}
        
        # Non-matching node
        non_matching_node = Mock()
        non_matching_node.metadata = {"user_uuid": "user456", "other_field": "value"}
        
        self.assertTrue(retriever._node_matches_filters(matching_node))
        self.assertFalse(retriever._node_matches_filters(non_matching_node))
    
    def test_node_matches_filters_or_condition(self):
        """Test node matching with OR filter conditions."""
        filters = {
            "$or": [
                {"user_uuid": "user123"},
                {"team_id": "team456"}
            ]
        }
        retriever = RBACFilteredRetriever(self.base_retriever, self.user, filters=filters)
        
        # Node matching first condition
        node1 = Mock()
        node1.metadata = {"user_uuid": "user123"}
        
        # Node matching second condition
        node2 = Mock()
        node2.metadata = {"team_id": "team456"}
        
        # Node matching neither condition
        node3 = Mock()
        node3.metadata = {"user_uuid": "user789"}
        
        self.assertTrue(retriever._node_matches_filters(node1))
        self.assertTrue(retriever._node_matches_filters(node2))
        self.assertFalse(retriever._node_matches_filters(node3))
    
    def test_metadata_matches_condition_in_operator(self):
        """Test metadata matching with $in operator."""
        filters = {"team_id": {"$in": ["team1", "team2"]}}
        retriever = RBACFilteredRetriever(self.base_retriever, self.user, filters=filters)
        
        # Matching metadata
        matching_node = Mock()
        matching_node.metadata = {"team_id": "team1"}
        
        # Non-matching metadata
        non_matching_node = Mock()
        non_matching_node.metadata = {"team_id": "team3"}
        
        self.assertTrue(retriever._node_matches_filters(matching_node))
        self.assertFalse(retriever._node_matches_filters(non_matching_node))


class RBACIntegrationTest(TestCase):
    """Integration tests for RBAC functionality."""
    
    def setUp(self):
        """Set up integration test data."""
        # Create users
        self.admin_user = User.objects.create_user(
            email='admin@test.com',
            username='admin',
            password='testpass123'
        )
        self.regular_user = User.objects.create_user(
            email='user@test.com',
            username='user', 
            password='testpass123'
        )
        self.external_user = User.objects.create_user(
            email='external@test.com',
            username='external',
            password='testpass123'
        )
        
        # Create team and membership
        self.team = Team.objects.create(name="Test Team", slug="test-team")
        Membership.objects.create(user=self.admin_user, team=self.team, role="admin")
        Membership.objects.create(user=self.regular_user, team=self.team, role="member")
        
        # Create knowledge base
        self.kb = KnowledgeBase.objects.create(
            name="Test KB",
            knowledgebase_id="test-kb-integration",
            uploaded_by=self.admin_user
        )
        
        # Create team permission
        KnowledgeBasePermission.objects.create(
            knowledge_base=self.kb,
            team=self.team,
            role=KnowledgeBasePermission.ROLE_EDITOR
        )
    
    def test_full_rbac_flow_admin(self):
        """Test complete RBAC flow for admin user."""
        # Admin should have owner access
        can_access = RBACService.can_user_access_knowledge_base(self.admin_user, "test-kb-integration")
        self.assertTrue(can_access)
        
        permission_level = RBACService.get_permission_level(self.admin_user, "test-kb-integration")
        self.assertEqual(permission_level, KnowledgeBasePermission.ROLE_OWNER)
        
        # Should get comprehensive filters
        filters = RBACService.get_user_accessible_filters(self.admin_user)
        self.assertIn("$or", filters)
    
    def test_full_rbac_flow_team_member(self):
        """Test complete RBAC flow for team member."""
        # Team member should have editor access through team permission
        can_access = RBACService.can_user_access_knowledge_base(self.regular_user, "test-kb-integration")
        self.assertTrue(can_access)
        
        permission_level = RBACService.get_permission_level(self.regular_user, "test-kb-integration")
        self.assertEqual(permission_level, KnowledgeBasePermission.ROLE_EDITOR)
    
    def test_full_rbac_flow_external_user(self):
        """Test complete RBAC flow for external user."""
        # External user should have no access
        can_access = RBACService.can_user_access_knowledge_base(self.external_user, "test-kb-integration")
        self.assertFalse(can_access)
        
        permission_level = RBACService.get_permission_level(self.external_user, "test-kb-integration")
        self.assertIsNone(permission_level)
        
        # Should only get filters for their own documents
        filters = RBACService.get_user_accessible_filters(self.external_user)
        # External user has no team, so filters should be minimal
        self.assertIsInstance(filters, dict)