import logging
from logging import Logger
from typing import Any, Dict, Optional
from uuid import uuid4

from django.utils import timezone
from slack_sdk.oauth.state_store import OAuthStateStore

from apps.slack_integration.models import SlackOAuthState


class DjangoOAuthStateStore(OAuthStateStore):
    """Django implementation of OAuthStateStore that preserves team_id through the OAuth flow"""
    
    def __init__(
        self,
        expiration_seconds: int = 600,  # Default 10 minutes
        logger: Optional[Logger] = None,
    ):
        self.expiration_seconds = expiration_seconds
        self._logger = logger or logging.getLogger(__name__)

    @property
    def logger(self) -> Logger:
        return self._logger

    def issue(self, team_id: str = None) -> str:
        """
        Issue a new OAuth state and associate it with an internal team ID
        
        Args:
            team_id: The internal team ID to associate with this state
        
        Returns:
            str: The unique state string
        """
        state = str(uuid4())
        expire_at = timezone.now() + timezone.timedelta(seconds=self.expiration_seconds)
        
        # Save the state with the team ID
        SlackOAuthState.objects.create(
            state=state, 
            expire_at=expire_at,
            team_id=team_id
        )
        
        self.logger.debug(f"Issued new OAuth state: {state} for team_id: {team_id}")
        return state

    def consume(self, state: str) -> Optional[Dict[str, Any]]:
        """
        Consume an OAuth state and return the associated team ID
        
        Args:
            state: The state string to consume
            
        Returns:
            dict: Dictionary containing team_id if found, otherwise None
        """
        try:
            # Find valid states that haven't expired yet
            valid_states = SlackOAuthState.objects.filter(
                state=state, 
                expire_at__gte=timezone.now()
            )
            
            if valid_states.exists():
                # Get the state object before deleting it
                state_obj = valid_states.first()
                team_id = state_obj.team_id
                
                # Delete the state to prevent reuse
                valid_states.delete()
                
                self.logger.debug(f"Consumed valid OAuth state: {state}, retrieved team_id: {team_id}")
                
                # Return team_id in the result
                return {"team_id": team_id} if team_id else {}
            else:
                # Clean up expired states
                SlackOAuthState.objects.filter(state=state).delete()
                self.logger.warning(f"Attempted to consume invalid/expired OAuth state: {state}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error consuming OAuth state: {e}")
            return None