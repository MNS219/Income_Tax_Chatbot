# build_index.py

import json
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
import pickle

with open("final_output_parser2.json") as f:
    data = json.load(f)

documents = []
texts = []

for sec in data:
    text = " ".join(
        sec.get("eligibility", []) +
        sec.get("conditions", []) +
        sec.get("exceptions", []) +
        sec.get("investments", [])
    )

    if text.strip():
        documents.append({
            "section": sec["section"],
            "text": text
        })
        texts.append(text)

model = SentenceTransformer("all-MiniLM-L6-v2")
embeddings = model.encode(texts, convert_to_numpy=True)

index = faiss.IndexFlatL2(embeddings.shape[1])
index.add(embeddings)

# 💾 SAVE
faiss.write_index(index, "faiss.index")

with open("docs.pkl", "wb") as f:
    pickle.dump(documents, f)

print("✅ Index built and saved")