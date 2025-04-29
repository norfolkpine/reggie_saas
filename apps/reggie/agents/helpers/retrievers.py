# apps/reggie/helpers/retrievers.py

from llama_index.core.retrievers import BaseRetriever

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
