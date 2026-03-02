# query_rag.py

import faiss
import pickle
from sentence_transformers import SentenceTransformer

# 🔥 LOAD instead of rebuild
index = faiss.read_index("faiss.index")

with open("docs.pkl", "rb") as f:
    documents = pickle.load(f)

model = SentenceTransformer("all-MiniLM-L6-v2")

def retrieve(query, k=5):
    if query.lower().startswith("section"):
        return [
            doc for doc in documents
            if doc["section"].lower() == query.lower()
        ]

    query_vec = model.encode([query])
    D, I = index.search(query_vec, k)

    return [documents[i] for i in I[0]]