# apps/reggie/helpers/retrievers.py

import logging
from typing import Any

from llama_index.core.retrievers import BaseRetriever

logger = logging.getLogger(__name__)


class ManualHybridRetriever(BaseRetriever):
    """
    A manual hybrid retriever: combines semantic + keyword retrieval results.
    """

    def __init__(self, semantic_retriever, keyword_retriever, alpha=0.5):
        self.semantic_retriever = semantic_retriever
        self.keyword_retriever = keyword_retriever
        self.alpha = alpha  # 0.5 = 50/50 balance between semantic and keyword

    def _retrieve(self, query: str):
        semantic_nodes = self.semantic_retriever.retrieve(query)
        keyword_nodes = self.keyword_retriever.retrieve(query)

        combined = []

        if semantic_nodes:
            combined.extend(semantic_nodes[: int(len(semantic_nodes) * self.alpha)])

        if keyword_nodes:
            combined.extend(keyword_nodes)

        return combined


class RBACFilteredRetriever(BaseRetriever):
    """
    A retriever that applies RBAC filtering to ensure users only access permitted content.

    This retriever wraps another retriever and applies metadata filters based on
    user permissions, team memberships, and knowledge base access.
    """

    def __init__(self, base_retriever: BaseRetriever, user, filters: dict[str, Any] | None = None):
        """
        Initialize the RBAC filtered retriever.

        Args:
            base_retriever: The underlying retriever to wrap
            user: The user object for permission checking
            filters: Optional pre-computed RBAC filters (if None, will be computed from user)
        """
        super().__init__()
        self.base_retriever = base_retriever
        self.user = user

        # If filters not provided, compute them
        if filters is None and user:
            from apps.reggie.services.rbac_service import RBACService

            self.filters = RBACService.get_user_accessible_filters(user)
        else:
            self.filters = filters or {}

    def _retrieve(self, query: str, **kwargs) -> list:
        """
        Retrieve documents with RBAC filtering applied.

        Args:
            query: The search query
            **kwargs: Additional retrieval parameters

        Returns:
            List of filtered nodes/documents
        """
        # If no filters, return empty results (no access)
        if not self.filters:
            logger.warning(f"No RBAC filters for user {self.user.id if self.user else 'anonymous'}")
            return []

        # Apply metadata filters to the retrieval
        if hasattr(self.base_retriever, "retrieve_with_metadata_filters"):
            # If the base retriever supports metadata filtering directly
            nodes = self.base_retriever.retrieve_with_metadata_filters(query, metadata_filters=self.filters, **kwargs)
        else:
            # Otherwise, retrieve and filter manually
            nodes = self.base_retriever.retrieve(query, **kwargs)
            nodes = self._filter_nodes_by_rbac(nodes)

        return nodes

    def _filter_nodes_by_rbac(self, nodes: list) -> list:
        """
        Manually filter nodes based on RBAC permissions.

        Args:
            nodes: List of retrieved nodes

        Returns:
            Filtered list of nodes
        """
        if not self.filters:
            return []

        filtered_nodes = []

        for node in nodes:
            if self._node_matches_filters(node):
                filtered_nodes.append(node)

        logger.debug(f"RBAC filtering: {len(nodes)} nodes -> {len(filtered_nodes)} after filtering")
        return filtered_nodes

    def _node_matches_filters(self, node) -> bool:
        """
        Check if a node matches the RBAC filters.

        Args:
            node: The node to check

        Returns:
            Boolean indicating if the node passes filters
        """
        # Get node metadata
        metadata = getattr(node, "metadata", {})
        if not metadata:
            return False

        # Handle OR logic in filters
        if "$or" in self.filters:
            for condition in self.filters["$or"]:
                if self._metadata_matches_condition(metadata, condition):
                    return True
            return False
        else:
            # Single condition
            return self._metadata_matches_condition(metadata, self.filters)

    def _metadata_matches_condition(self, metadata: dict, condition: dict) -> bool:
        """
        Check if metadata matches a filter condition.

        Args:
            metadata: Node metadata
            condition: Filter condition

        Returns:
            Boolean indicating match
        """
        for key, value in condition.items():
            if key not in metadata:
                return False

            # Handle $in operator for list membership
            if isinstance(value, dict) and "$in" in value:
                if metadata[key] not in value["$in"]:
                    return False
            # Direct equality check
            elif metadata[key] != value:
                return False

        return True
