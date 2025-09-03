"""
RBAC Service for managing access control in the vector database.

This service handles Role-Based Access Control (RBAC) for the RAG system,
ensuring users can only access vectors they have permission to see.
"""

from typing import List, Dict, Any, Optional
from django.contrib.auth import get_user_model
from apps.teams.models import Team, Membership
from apps.reggie.models import KnowledgeBase, KnowledgeBasePermission
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class RBACService:
    
    @staticmethod
    def get_user_accessible_filters(user) -> Dict[str, Any]:
        """
        Get all vector DB filters for a user's accessible content.
        
        Args:
            user: The user object to get filters for
            
        Returns:
            Dictionary containing PGVector-compatible metadata filters
        """
        if not user or user.is_anonymous:
            return {}
            
        filters = []
        
        # 1. User's own documents (always accessible)
        if hasattr(user, 'uuid'):
            filters.append({"user_uuid": str(user.uuid)})
        elif hasattr(user, 'id'):
            filters.append({"user_uuid": str(user.id)})
        
        # 2. Team documents (accessible to all team members)
        try:
            memberships = Membership.objects.filter(user=user).select_related('team')
            team_ids = [str(m.team.id) for m in memberships]
            if team_ids:
                filters.append({"team_id": {"$in": team_ids}})
        except Exception as e:
            logger.error(f"Error fetching team memberships for user {user.id}: {e}")
        
        # 3. Knowledge base access (through team permissions)
        try:
            # Get all teams the user belongs to
            user_teams = Team.objects.filter(members=user)
            
            # Get knowledge bases accessible through team permissions
            kb_permissions = KnowledgeBasePermission.objects.filter(
                team__in=user_teams
            ).select_related('knowledge_base')
            
            kb_ids = [perm.knowledge_base.knowledgebase_id for perm in kb_permissions 
                     if perm.knowledge_base.knowledgebase_id]
            
            if kb_ids:
                filters.append({"knowledgebase_id": {"$in": kb_ids}})
        except Exception as e:
            logger.error(f"Error fetching knowledge base permissions for user {user.id}: {e}")
        
        # 4. Project access (if projects are team-based)
        try:
            from apps.reggie.models import TeamProject
            user_projects = TeamProject.objects.filter(team__in=user_teams)
            project_ids = [str(p.id) for p in user_projects]
            if project_ids:
                filters.append({"project_id": {"$in": project_ids}})
        except Exception as e:
            logger.debug(f"Project filtering not available or error: {e}")
        
        # Combine all filters with OR logic
        if not filters:
            # No filters means no access
            return {"user_uuid": "no_access"}
        elif len(filters) == 1:
            return filters[0]
        else:
            return {"$or": filters}
    
    @staticmethod
    def get_user_knowledge_bases(user) -> List[KnowledgeBase]:
        """
        Get all knowledge bases accessible to a user.
        
        Args:
            user: The user object
            
        Returns:
            List of KnowledgeBase objects the user can access
        """
        if not user or user.is_anonymous:
            return []
        
        # Get user's teams
        user_teams = Team.objects.filter(members=user)
        
        # Get knowledge bases through permissions
        kb_permissions = KnowledgeBasePermission.objects.filter(
            team__in=user_teams
        ).select_related('knowledge_base')
        
        # Also include knowledge bases directly uploaded by the user
        from django.db.models import Q
        user_kbs = KnowledgeBase.objects.filter(
            Q(permissions__team__in=user_teams) |  # Through team permissions
            Q(uploaded_by=user)  # Directly uploaded
        ).distinct()
        
        return list(user_kbs)
    
    @staticmethod
    def can_user_access_knowledge_base(user, knowledge_base_id: str) -> bool:
        """
        Check if a user can access a specific knowledge base.
        
        Args:
            user: The user object
            knowledge_base_id: The knowledgebase_id string
            
        Returns:
            Boolean indicating access permission
        """
        if not user or user.is_anonymous:
            return False
        
        try:
            kb = KnowledgeBase.objects.get(knowledgebase_id=knowledge_base_id)
            
            # Check if user uploaded it
            if kb.uploaded_by == user:
                return True
            
            # Check team permissions
            user_teams = Team.objects.filter(members=user)
            return KnowledgeBasePermission.objects.filter(
                knowledge_base=kb,
                team__in=user_teams
            ).exists()
        except KnowledgeBase.DoesNotExist:
            return False
        except Exception as e:
            logger.error(f"Error checking KB access: {e}")
            return False
    
    @staticmethod
    def get_permission_level(user, knowledge_base_id: str) -> Optional[str]:
        """
        Get the user's permission level for a knowledge base.
        
        Args:
            user: The user object
            knowledge_base_id: The knowledgebase_id string
            
        Returns:
            Permission level string ('viewer', 'editor', 'owner') or None
        """
        if not user or user.is_anonymous:
            return None
        
        try:
            kb = KnowledgeBase.objects.get(knowledgebase_id=knowledge_base_id)
            
            # Owner has full permissions
            if kb.uploaded_by == user:
                return KnowledgeBasePermission.ROLE_OWNER
            
            # Check team permissions
            user_teams = Team.objects.filter(members=user)
            permission = KnowledgeBasePermission.objects.filter(
                knowledge_base=kb,
                team__in=user_teams
            ).order_by('-role').first()  # Get highest permission level
            
            return permission.role if permission else None
        except KnowledgeBase.DoesNotExist:
            return None
        except Exception as e:
            logger.error(f"Error getting permission level: {e}")
            return None
    
    @staticmethod
    def validate_ingestion_metadata(user, metadata: Dict[str, Any]) -> Dict[str, str]:
        """
        Validate and enrich metadata for document ingestion.
        
        Args:
            user: The user performing the ingestion
            metadata: The metadata dictionary from the ingestion request
            
        Returns:
            Validated metadata dictionary
            
        Raises:
            ValueError: If validation fails
        """
        errors = {}
        
        # Validate team access
        if metadata.get('team_id'):
            if not Team.objects.filter(
                id=metadata['team_id'],
                members=user
            ).exists():
                errors['team_id'] = "You don't have access to the specified team"
        
        # Validate knowledge base access
        if metadata.get('knowledgebase_id'):
            if not RBACService.can_user_access_knowledge_base(user, metadata['knowledgebase_id']):
                errors['knowledgebase_id'] = "You don't have access to the specified knowledge base"
        
        # Validate project access (if applicable)
        if metadata.get('project_id'):
            try:
                from apps.reggie.models import TeamProject
                user_teams = Team.objects.filter(members=user)
                if not TeamProject.objects.filter(
                    id=metadata['project_id'],
                    team__in=user_teams
                ).exists():
                    errors['project_id'] = "You don't have access to the specified project"
            except Exception as e:
                logger.debug(f"Project validation skipped: {e}")
        
        return errors