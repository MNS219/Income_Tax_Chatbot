# 📊 Income Tax KG + RAG Chatbot

A conversational chatbot that answers Indian income tax queries by combining a **Knowledge Graph (Neo4j)**, **Vector Search (FAISS)**, and a **local LLM (Ollama)**. Built on the Income Tax Act, 1961.

---

## 🧠 Project Overview

The system combines:
- 📄 **PDF Parsing** → Extracts and structures legal data from the Income Tax Act
- 🧩 **Knowledge Graph (Neo4j)** → Stores structured relationships between sections, eligibility, conditions, limits, investments
- 🔍 **Vector Search (FAISS)** → Semantic retrieval of relevant sections
- 🤖 **LLM (Ollama / llama3.1:8b)** → Generates natural language answers
- 🧠 **Chat Memory** → Maintains last 5 turns for follow-up questions

---

## 🔁 End-to-End Flow
```
Income Tax PDF
     ↓
parser.py — extract + structure sections
     ↓
final_output_parser2.json
     ↓                        ↓
load_kg.py               build_index.py
     ↓                        ↓
Neo4j (KG)              FAISS + docs.pkl
     ↓                        ↓
kg.py ←————— chatbot.py ————→ query_rag.py
                  ↓
             Ollama (LLM)
                  ↓
          Chatbot response
```

---

## ⚙️ Execution Order

### 1️⃣ Parse PDF → Structured JSON
```bash
python parser.py
```
Output: `final_output_parser2.json`

### 2️⃣ Load Knowledge Graph into Neo4j
```bash
python load_kg.py
```

### 3️⃣ Build FAISS Index
```bash
python build_index.py
```

### 4️⃣ Run Chatbot
```bash
python chatbot.py
```

---

## 📁 File Reference

### `parser.py`
- Extracts text from the Income Tax Act PDF
- Splits into individual sections using regex
- Uses LLM (Ollama) to extract structured fields:
  - `eligibility` — who can claim
  - `conditions` — requirements to claim
  - `exceptions` — when deduction is disallowed
  - `investments` — eligible instruments/schemes
  - `limits` — monetary caps and maximums
- Filters out footnotes and amendment notes
- Saves to `final_output_parser2.json` incrementally (resume-safe)

### `load_kg.py`
- Reads `final_output_parser2.json`
- Creates Neo4j nodes:
  - `Section`, `Eligibility`, `Condition`, `Exception`, `Investment`, `Limit`
- Creates relationships:
  - `HAS_ELIGIBILITY`, `HAS_CONDITION`, `HAS_EXCEPTION`, `HAS_INVESTMENT`, `HAS_LIMIT`

### `kg.py`
- Queries Neo4j for a given section
- Returns structured KG data (eligibility, conditions, limits etc.)
- Used by `chatbot.py` to augment retrieval context

### `build_index.py`
- Loads `final_output_parser2.json`
- Converts each section to a text document
- Generates embeddings using `all-MiniLM-L6-v2`
- Builds and saves FAISS index → `faiss.index` + `docs.pkl`

### `query_rag.py`
- Loads FAISS index and `docs.pkl` at startup
- Supports two retrieval modes:
  - **Exact match** — for direct section queries (`Section 80C`)
  - **Semantic search** — for natural language queries

### `chatbot.py`
- Main orchestrator with chat memory (last 5 turns)
- Detects section references including `sec 80c`, `u/s 80C`, bare `80C`
- Handles multi-section queries (`Compare 80C and 80D`)
- Calls `query_rag.py` for FAISS retrieval
- Calls `kg.py` for Neo4j graph expansion
- Combines both into augmented context
- Sends prompt to Ollama → returns structured answer

---

## 🛠️ Requirements
```bash
pip install pdfplumber sentence-transformers faiss-cpu neo4j requests pydantic tqdm
```

- Ollama running locally with `llama3.1:8b` pulled
- Neo4j running locally on `bolt://localhost:7687`

---

## 💬 Example Queries
```
What is Section 80C?
Compare Section 80C and 80D
Who is eligible for Section 80D?
What is the limit for Section 80C?
What is income tax?
sec 80c
u/s 80C
```

