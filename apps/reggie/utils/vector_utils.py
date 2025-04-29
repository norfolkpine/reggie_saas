import numpy as np
from django.db import connection

def insert_embedding(vector_table_name: str, content_id: str, content: str, embedding: np.ndarray, metadata: dict = None):
    """
    Insert an embedding into the vector table.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT INTO {vector_table_name}
            (content_id, content, embedding, metadata)
            VALUES (%s, %s, %s, %s)
            """,
            [content_id, content, embedding.tolist(), metadata],
        )

def search_similar(vector_table_name: str, query_embedding: np.ndarray, limit: int = 5):
    """
    Search for similar embeddings using cosine similarity.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT content_id, content, metadata,
                   1 - (embedding <=> %s) as similarity
            FROM {vector_table_name}
            ORDER BY embedding <=> %s
            LIMIT %s
            """,
            [query_embedding.tolist(), query_embedding.tolist(), limit],
        )

        return cursor.fetchall()
