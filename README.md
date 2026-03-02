# 📊 Income Tax KG + RAG Chatbot

This project builds a **Knowledge Graph (KG)** from the Income Tax Act PDF and integrates it with a **RAG (Retrieval-Augmented Generation)** pipeline and a local LLM (via Ollama) to answer tax-related queries.

---

# 🧠 Project Overview

The system combines:

- 📄 PDF Parsing → Extract structured legal data  
- 🧩 Knowledge Graph (Neo4j) → Structured relationships  
- 🔍 Vector Search (FAISS) → Semantic retrieval  
- 🤖 LLM (Ollama) → Natural language answers  

---

# 🔁 End-to-End Flow
# 📊 Income Tax KG + RAG Chatbot

This project builds a **Knowledge Graph (KG)** from the Income Tax Act PDF and integrates it with a **RAG (Retrieval-Augmented Generation)** pipeline and a local LLM (via Ollama) to answer tax-related queries.

---

# 🧠 Project Overview

The system combines:

- 📄 PDF Parsing → Extract structured legal data  
- 🧩 Knowledge Graph (Neo4j) → Structured relationships  
- 🔍 Vector Search (FAISS) → Semantic retrieval  
- 🤖 LLM (Ollama) → Natural language answers  

---

# 🔁 End-to-End Flow
Income Tax PDF\
↓\
Structured JSON (parser.py)\
↓\
Knowledge Graph (Neo4j)\
↓\
FAISS Vector Index\
↓\
RAG Retrieval\
↓\
LLM (Ollama)\
↓\
Chatbot Response


---

# ⚙️ Execution Order

Run the files in this order:

---

## 1️⃣ Parse PDF → Structured JSON

```bash
python parser.py
```
Output:
```
final_output_parser2.json
```

## 2️⃣ Load Knowledge Graph into Neo4j
```
python load_kg.py
```
## 3️⃣ Build FAISS Index
```
python build_index.py
```
## 4️⃣ Run Chatbot
```
python chatbot.py
```

### ``parser.py``

- Extracts text from PDF
- Splits into sections
- Uses LLM to structure:
  - eligibility
  - conditions
  - exceptions
  - investments

### ``load_kg.py``
- Loads JSON into Neo4j
- Creates nodes:
    - Section
    - Eligibility
    - Condition
    - Exception
    - Investment

### ``kg.py``
- Queries Neo4j graph
- Returns related nodes for a section

### ``build_index.py``
- Converts JSON → text documents
- Generates embeddings
- Builds FAISS index

### ``query_rag.py``
- Handles retrieval
- Supports:
    - exact section match
    - semantic search

### ``chatbot.py``
- Main chatbot logic
- Combines:
    - RAG (FAISS)
    - KG (Neo4j)
    - LLM (Ollama)
- Maintains short chat memory