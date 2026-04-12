import pdfplumber
import faiss
import pickle
import re
import numpy as np
from sentence_transformers import SentenceTransformer

CHUNK_SIZE = 800
OVERLAP = 150


def extract_and_chunk(pdf_path):
    chunks = []
    current_section = "General"

    with pdfplumber.open(pdf_path) as pdf:
        full_text_by_page = []

        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text_by_page.append(text)

    full_text = "\n".join(full_text_by_page)

    # split by section headers
    pattern = r"(?:^|\n)(\d{1,3}[A-Z]{0,4})\.\s"
    matches = list(re.finditer(pattern, full_text, re.MULTILINE))

    print(f"Found {len(matches)} section boundaries in PDF")

    for i, match in enumerate(matches):
        section_num = match.group(1)
        section_name = f"Section {section_num}"

        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        section_text = full_text[start:end].strip()

        # skip footnote-only sections
        lines = section_text.split("\n")
        footnote_lines = sum(
            1 for l in lines
            if any(x in l.lower() for x in ["w.e.f", "w.r.e.f", "omtt by", "ins. by", "sub. by", "act no."])
        )
        if len(lines) > 0 and footnote_lines / len(lines) > 0.6:
            continue

        # skip very short sections
        if len(section_text.split()) < 20:
            continue

        # chunk the section text with overlap
        chunk_start = 0
        while chunk_start < len(section_text):
            chunk_end = chunk_start + CHUNK_SIZE
            chunk = section_text[chunk_start:chunk_end].strip()

            if chunk and len(chunk.split()) > 15:
                chunks.append({
                    "section": section_name,
                    "text": chunk,
                    "raw_text": chunk,
                    "chunk_index": len(chunks)
                })

            chunk_start += CHUNK_SIZE - OVERLAP

    return chunks


def build_index(pdf_path):
    print("Extracting and chunking PDF...")
    chunks = extract_and_chunk(pdf_path)
    print(f"Total chunks: {len(chunks)}")

    unique_sections = len(set(c["section"] for c in chunks))
    print(f"Sections covered: {unique_sections}")

    texts = [c["text"] for c in chunks]

    model = SentenceTransformer("all-MiniLM-L6-v2")
    print("Encoding embeddings...")
    embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=True)

    index = faiss.IndexFlatL2(embeddings.shape[1])
    index.add(embeddings)

    faiss.write_index(index, "faiss.index")
    with open("docs.pkl", "wb") as f:
        pickle.dump(chunks, f)

    print(f"✅ Done — {len(chunks)} chunks from {unique_sections} sections indexed")


if __name__ == "__main__":
    build_index("income-tax.pdf")