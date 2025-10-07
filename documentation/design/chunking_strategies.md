### Analysis of Document-Specific Chunking Strategies

The system employs a sophisticated, modular design where each document type has its own specialized chunking logic located in the `rag/app` directory. This allows the application to go far beyond simple, fixed-size windowing and instead create chunks that respect the semantic structure of the source document.

Here is a breakdown of the chunking strategy for each key document type:

---

#### **1. Paper (`paper.py`)**

This is one of the most advanced chunking methods, designed to understand the structure of academic papers.

*   **Abstract as a Priority Chunk**: The parser first identifies and extracts the paper's **abstract**. This abstract is treated as a single, complete chunk and is flagged as highly important. This ensures the core summary of the paper is never fragmented.
*   **Section-Based Grouping**: The primary chunking strategy for the main content is based on the document's outline. The logic detects section titles (e.g., "1. Introduction", "2. Related Work", "2.1 Methodology"). It then groups all the text that falls between two consecutive top-level titles. For example, all of section 2, including subsections 2.1 and 2.2, will be part of the same logical chunk before being passed to the tokenizer. This preserves the contextual integrity of each section.
*   **Table and Figure Extraction**: Tables and figures are identified by the `deepdoc` parser and extracted separately. They are not mixed in with the main text chunks.

---

#### **2. Book (`book.py`)**

The book chunker focuses on preserving the narrative flow and chapter-based structure.

*   **Table of Contents (ToC) Analysis**: It first parses the book's ToC to identify chapter titles and their page numbers.
*   **Chapter-by-Chapter Processing**: The book is processed one chapter at a time. The text for each chapter is extracted and then passed to a `tokenize_chunks` function.
*   **Hierarchical Splitting**: Within each chapter, the text is split using a hierarchical list of delimiters, starting with the most significant breaks (e.g., double newlines `\n\n`) and moving to smaller ones. This creates chunks that are more likely to align with paragraphs and natural breaks in the text.

---

#### **3. Presentation (`presentation.py`)**

This chunker is optimized for slide-based content like PowerPoint presentations.

*   **One Slide, One Chunk**: The fundamental rule is that **each slide becomes a single chunk**. All the text from a single slide is concatenated together.
*   **Speaker Notes Inclusion**: If speaker notes are present for a slide, they are appended to the slide's text, enriching the content of that chunk. This is crucial as notes often contain the detailed information that the slide itself only hints at.

---

#### **4. Q&A (`qa.py`)**

This parser is designed for structured question-and-answer formats, like FAQ documents.

*   **Question-Answer Pairing**: The logic iterates through the document, identifying distinct questions and their corresponding answers.
*   **Atomic Q&A Chunks**: Each **question-answer pair is treated as a single, atomic chunk**. The question and answer are concatenated into one text block. This ensures that the direct context between a question and its answer is always preserved for retrieval.

---

#### **5. Manual (`manual.py`)**

The manual chunker is similar to the book chunker but adapted for technical documentation.

*   **ToC-Driven Sectioning**: Like the book parser, it heavily relies on the Table of Contents to understand the document's structure.
*   **Section-Based Chunking**: It groups text based on the sections and subsections defined in the ToC. All content under a specific heading (e.g., "3.1. Installing the Software") is chunked together, respecting the document's hierarchy.

---

#### **6. Naive (`naive.py`)**

This is the default, fallback chunker for documents that don't fit the other specialized categories or for when a simple approach is desired.

*   **Delimiter-Based Splitting**: It uses a straightforward, hierarchical splitting method. The text is first split by a list of major delimiters (e.g., `\n\n`, `\n`, `。`, `. `).
*   **Token-Length Enforcement**: After the initial split, the resulting text segments are grouped together to form chunks that are close to a target token length (defined by `chunk_token_num`, typically around 512). It will merge smaller segments or split larger ones to meet this target, but the initial splits are guided by the delimiters.