import os
import deepdoctection as dd
import fitz
from chunking_strategies import (
    get_text_splitter
)
from llama_index.core import Document
from parser.pdf_parser import parse_pdf
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
pdf_path = os.path.join(BASE_DIR, "2.pdf")

pdf_doc = fitz.open(pdf_path)
pdf_doc.close()
payload = {
    "strategy_id": "paper",
    "strategy_config": {}
}
text_splitter = get_text_splitter(payload["strategy_id"], payload["strategy_config"])
documents = parse_pdf(pdf_path)
all_chunks=[]
for doc in documents:
    text_chunks = text_splitter.split_text(doc.text)
    all_chunks.extend([Document(text=json.dumps(chunk)) for chunk in text_chunks if chunk])

for i, chunk in enumerate(all_chunks):
    print(f"Chunk {i+1}:\n{chunk.text}\n{'-'*40}")

with open("output", 'w') as file:
    # Iterate through the array and write each element to a new line
    for i, chunk in enumerate(all_chunks):
        file.write(f"Chunk {i+1}:\n{chunk.text}\n{'-'*40}")