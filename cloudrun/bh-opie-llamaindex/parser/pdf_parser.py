from pypdf import PdfReader as pdf2_read
import logging
import os
from llama_index.core import Document
import fitz

def parse_pdf(file_path: str) -> list[Document]:
    pdf_doc = fitz.open(file_path)
    documents = []
    for page_num, page in enumerate(pdf_doc):
        text = page.get_text()
        documents.append(Document(text=text))
    return documents

class PlainParser:
    def __call__(self, filename, from_page=0, to_page=100000, **kwargs):
        self.outlines = []
        lines = []
        try:
            self.pdf = pdf2_read(filename if isinstance(filename, str) else BytesIO(filename))
            for page in self.pdf.pages[from_page:to_page]:
                lines.extend([t for t in page.extract_text().split("\n")])

            outlines = self.pdf.outline

            def dfs(arr, depth):
                for a in arr:
                    if isinstance(a, dict):
                        self.outlines.append((a["/Title"], depth))
                        continue
                    dfs(a, depth + 1)

            dfs(outlines, 0)
        except Exception:
            logging.exception("Outlines exception")
        if not self.outlines:
            logging.warning("Miss outlines")

        return [(line, "") for line in lines], []

    def crop(self, ck, need_position):
        raise NotImplementedError

    @staticmethod
    def remove_tag(txt):
        raise NotImplementedError