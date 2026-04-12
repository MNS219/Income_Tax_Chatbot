import faiss
import pickle
from sentence_transformers import SentenceTransformer

index_path = "faiss.index"

index = faiss.read_index(str(index_path))

with open("docs.pkl", "rb") as f:
    documents = pickle.load(f)

model = SentenceTransformer("all-MiniLM-L6-v2")


def retrieve(query, k=5):
    # exact section match — return all chunks for that section
    if query.lower().startswith("section"):
        results = [
            doc for doc in documents
            if doc["section"].lower() == query.lower()
        ]
        if results:
            # return first k chunks (they cover the section in order)
            return results[:k]

    # semantic search across all chunks
    query_vec = get_model().encode([query])
    D, I = index.search(query_vec, k)

    # filter out -1 (not enough results)
    return [documents[i] for i in I[0] if i != -1]