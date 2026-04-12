import re
import requests
from query_rag import retrieve
from kg import expand_with_kg

# -------------------------------
# MEMORY
# -------------------------------
chat_history = []


# -------------------------------
# OUT-OF-SCOPE DETECTOR
# -------------------------------
OUT_OF_SCOPE_KEYWORDS = [
    "gst", "goods and services tax", "companies act",
    "trade license", "repo rate", "rbi", "reserve bank",
    "sebi", "customs duty", "excise duty", "vat",
    "startup india", "dpiit", "fema", "company registration",
    "shop act", "labour law", "esic", "gratuity act"
]

def is_out_of_scope(query):
    q = query.lower()
    return any(k in q for k in OUT_OF_SCOPE_KEYWORDS)


# -------------------------------
# EXTRACT SECTION
# -------------------------------
def extract_section(query):
    explicit  = re.findall(r"section\s*(\d+[a-zA-Z]*)", query.lower())
    shorthand = re.findall(r"(?:sec|u/s|us)\s*(\d+[a-zA-Z]*)", query.lower())
    implicit  = re.findall(r"(?:and|or|,)\s*(\d+[a-zA-Z]+)", query.lower())
    bare      = re.findall(r"(?<![a-zA-Z])(\d+[A-Z]+)(?![a-zA-Z])", query)

    all_matches = explicit + shorthand + implicit + bare
    if all_matches:
        seen, result = set(), []
        for m in all_matches:
            key = m.upper()
            if key not in seen:
                seen.add(key)
                result.append(f"Section {key}")
        return result
    return []


# -------------------------------
# GET LAST SECTION FROM HISTORY
# -------------------------------
def get_last_section_from_history():
    for q, a in reversed(chat_history):
        sections = extract_section(q)
        if sections:
            return sections
    return []


# -------------------------------
# BUILD HISTORY CONTEXT
# -------------------------------
def build_history_context():
    history_text = ""
    for q, a in chat_history[-5:]:
        history_text += f"User: {q}\nAssistant: {a}\n\n"
    return history_text


# -------------------------------
# GENERAL FALLBACK
# -------------------------------
GENERAL_ANSWERS = {
    "what is income tax":       "Income tax is a direct tax levied by the Government of India on income earned by individuals, HUFs, companies, and other entities during a financial year. It is governed by the Income Tax Act, 1961.",
    "what is tds":              "TDS (Tax Deducted at Source) is a mechanism where tax is deducted at the point of income generation before it is paid to the recipient. It is governed by Sections 192–206 of the Income Tax Act.",
    "what is a financial year": "A financial year in India runs from April 1st to March 31st of the following year. Income earned during this period is assessed in the Assessment Year (AY) that follows.",
    "how is income tax calculated": "Income tax is calculated on total taxable income after all eligible deductions, applied as per the slab rates for the financial year under the old or new tax regime.",
    "what is assessment year":  "An Assessment Year (AY) is the year in which income earned in the previous financial year is assessed and taxed. Income of FY 2023-24 is assessed in AY 2024-25.",
    "what is pan":              "PAN (Permanent Account Number) is a 10-digit alphanumeric identifier issued by the Income Tax Department, mandatory for filing returns and high-value financial transactions.",
}

def check_general(query):
    q = query.lower().strip().rstrip("?")
    for key, answer in GENERAL_ANSWERS.items():
        if key in q:
            return answer
    return None


# -------------------------------
# DEDUPE CHUNKS
# -------------------------------
def dedupe_chunks(docs):
    seen, result = set(), []
    for doc in docs:
        key = doc["text"][:120]
        if key not in seen:
            seen.add(key)
            result.append(doc)
    return result


# -------------------------------
# BUILD CONTEXT FROM DOCS + KG
# -------------------------------
def build_context(docs):
    context = ""
    seen_sections = set()

    for doc in docs:
        section = doc["section"]

        # --- RAG chunk (raw legal text from PDF) ---
        context += f"\n[{section}]\n{doc['text']}\n"

        # --- KG enrichment (once per unique section) ---
        if section not in seen_sections:
            seen_sections.add(section)
            kg = expand_with_kg(section)

            if not kg:
                continue

            enrichment = ""

            # raw_text from JSON (first 1000 chars of actual section)
            # use it only if it's different from what FAISS already returned
            raw = kg.get("raw_text", "").strip()
            if raw and raw[:80] not in doc["text"]:
                enrichment += f"\nSection text:\n{raw}\n"

            # description — one-line summary helps LLM orient
            desc = kg.get("description", "").strip()
            if desc:
                enrichment += f"\nDescription: {desc}\n"

            # structured fields — label each clearly
            field_map = {
                "eligibility": "Eligibility",
                "conditions":  "Conditions",
                "exceptions":  "Exceptions",
                "investments": "Eligible investments",
                "limits":      "Monetary limits",
            }
            for key, label in field_map.items():
                values = kg.get(key, [])
                if values:
                    enrichment += f"\n{label}:\n"
                    for v in values:
                        enrichment += f"  - {v}\n"

            if enrichment:
                context += f"\nKnowledge graph data for {section}:{enrichment}"

    return context


# -------------------------------
# GENERATE ANSWER
# -------------------------------
def generate_answer(query):
    if is_out_of_scope(query):
        answer = "This question is outside the scope of the Income Tax Act, 1961. I can only answer questions related to Indian income tax."
        chat_history.append((query, answer))
        return answer

    general = check_general(query)
    if general:
        chat_history.append((query, general))
        return general

    sections = extract_section(query)
    if not sections:
        sections = get_last_section_from_history()

    docs = []
    if sections:
        for section_name in sections:
            section_docs = retrieve(section_name)
            section_docs = [
                d for d in section_docs
                if d["section"].strip().lower() == section_name.strip().lower()
            ]
            docs.extend(section_docs)

    if not docs:
        docs = retrieve(query)

    docs = dedupe_chunks(docs)

    if not docs:
        answer = "I don't have specific information about this in my dataset. Please consult the Income Tax Act directly or a qualified tax professional."
        chat_history.append((query, answer))
        return answer

    context        = build_context(docs)
    history_context = build_history_context()

    prompt = f"""You are a helpful Indian income tax assistant.

Conversation history (for follow-up context only):
{history_context}

Retrieved context:
{context}

Question: {query}

Instructions:
- Answer primarily using the retrieved context, but you may use general knowledge of the Income Tax Act if needed for completeness.
- Use conversation history only to resolve follow-up references like "it", "the limit", "that section"

- Provide a clear, natural explanation (not overly formal or legalistic)
- Start with a short 1–2 sentence summary mentioning the section number
- Focus on the main provision first, then add key details

- Highlight important information such as limits, eligibility, and main rules clearly
- When limits are involved, clearly state what each limit applies to (e.g., self, family, parents) and avoid mixing categories
- Preserve relationships between information (explain what applies to whom, not just listing values)

- Prefer simple, practical language and rewrite legal phrases into everyday language
- Prioritize common real-world examples (e.g., PPF, ELSS, insurance, tuition fees)

- Avoid over-structuring:
  - Do NOT use fixed templates like "Eligibility", "Conditions", "Key details"
  - Use bullets or headings only if they clearly improve clarity
  - Prefer a natural paragraph-style explanation for simple questions

- Avoid unnecessary technical or rarely used sub-clauses unless essential
- Do not include excessive detail beyond what is useful to understand the section


- When multiple limits exist, do NOT combine them into a single “maximum limit”; clearly explain each category separately

- For comparison questions, focus on key differences directly instead of repeating full explanations of each section

- Avoid adding general advice (e.g., keeping records, filing tips) unless explicitly asked

- When asked for a specific field (e.g., "what is the limit"), answer concisely
- When comparing sections, focus on key differences directly instead of repeating full explanations

- Avoid repeating the same information in different forms; keep the answer concise and focused

- If the context does not contain enough information, say "I don't have specific information about this"
- Do NOT answer non-income-tax topics
"""
    res = requests.post(
        "http://localhost:11434/api/generate",
        json={"model": "llama3.1:8b", "prompt": prompt, "stream": False},
        timeout=120
    )

    answer = res.json()["response"]
    chat_history.append((query, answer))
    return answer




# -------------------------------
# EVAL WRAPPER
# -------------------------------
def get_eval_response(query: str) -> dict:
    try:
        answer, context = generate_answer(query)
        return {
            "answer": answer,
            "contexts": [context]
        }
    except Exception as e:
        return {
            "answer": f"ERROR: {str(e)}",
            "contexts": [context]
        }

# -------------------------------
# CHAT LOOP
# -------------------------------
if __name__ == "__main__":
    print("💬 Tax Chatbot Started (type 'exit' to quit)\n")
    while True:
        q = input("You: ").strip()
        if not q:
            continue
        if q.lower() in ["exit", "quit"]:
            print("👋 Goodbye!")
            break
        print(f"\nAssistant:\n{generate_answer(q)}\n")