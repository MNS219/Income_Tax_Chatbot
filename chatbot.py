import re
import requests
from query_rag import retrieve
from kg import expand_with_kg

# -------------------------------
# MEMORY (CHAT HISTORY)
# -------------------------------
chat_history = []


# -------------------------------
# EXTRACT SECTION
# -------------------------------
def extract_section(query):
    # Match explicit "section 80C" patterns
    explicit = re.findall(r"section\s*(\d+[a-zA-Z]*)", query.lower())
    
    # Match bare section numbers after "and", "or", ","
    implicit = re.findall(r"(?:and|or|,)\s*(\d+[a-zA-Z]+)", query.lower())

    # Match shorthand like "sec 80c", "u/s 80c"
    shorthand = re.findall(r"(?:sec|u/s|us)\s*(\d+[a-zA-Z]*)", query.lower())

    # Match bare section numbers like "80C" or "80D" with no prefix
    bare = re.findall(r"(?<![a-zA-Z])(\d+[A-Z]+)(?![a-zA-Z])", query)

    all_matches = explicit + implicit + shorthand + [b for b in bare]

    if all_matches:
        return list({f"Section {m.upper()}" for m in all_matches})  # dedupe
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
    "what is income tax": "Income tax is a direct tax levied by the Government of India on the income earned by individuals, HUFs, companies, and other entities during a financial year. It is governed by the Income Tax Act, 1961.",
    "what is tds": "TDS (Tax Deducted at Source) is a mechanism where tax is deducted at the point of income generation before the amount is paid to the recipient.",
    "what is a financial year": "A financial year in India runs from April 1st to March 31st of the following year. For tax purposes, income earned during this period is assessed in the Assessment Year (AY) that follows.",
    "how is income tax calculated": "Income tax in India is calculated based on your total taxable income after deductions. It is applied as per the applicable slab rates for the financial year under either the old or new tax regime.",
}

def check_general(query):
    q = query.lower().strip().rstrip("?")
    for key, answer in GENERAL_ANSWERS.items():
        if key in q:
            return answer
    return None


# -------------------------------
# GENERATE ANSWER
# -------------------------------
def generate_answer(query):
    general = check_general(query)
    if general:
        chat_history.append((query, general))
        return general

    sections = extract_section(query)

    # ✅ if no section in query, check history for last mentioned section
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

    # ✅ fallback to vector search if no docs found
    if not docs:
        docs = retrieve(query)

    if not docs:
        return "Sorry, I couldn't find relevant information for your question."

    context = ""

    for doc in docs:
        context += f"\n{doc['section']}:\n{doc['text']}\n"

        kg_data = expand_with_kg(doc["section"])
        if kg_data:
            context += "\n".join(kg_data) + "\n"

    history_context = build_history_context()

    prompt = f"""
You are a helpful Indian income tax assistant.

Conversation history (for follow-up context only):
{history_context}

Current Context (use THIS for your answer):
{context}

Question:
{query}

Instructions:
- Answer the CURRENT question using the Current Context above
- Only use Conversation history to understand follow-up references like "it", "that section", "the limit"
- Do NOT copy section names or content from Conversation history into your answer
- When explaining a section fully, group into: Eligibility, Investments, Limits, Conditions, Exceptions
- When asked about a specific field only (limit, investments, eligibility), answer only that field and mention which section it belongs to
- When comparing sections, give each section its own clearly labelled block
- Start your answer directly — do NOT say "To answer your question about Section X" or "Based on the context"
- Do NOT add outside knowledge not present in Current Context
- If a section is not found in Current Context, say "Section X not found in data" — do NOT guess
"""

    res = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": "llama3.1:8b",
            "prompt": prompt,
            "stream": False
        }
    )

    answer = res.json()["response"]
    chat_history.append((query, answer))
    return answer


# -------------------------------
# CHAT LOOP
# -------------------------------
if __name__ == "__main__":
    print("💬 Tax Chatbot Started (type 'exit' to quit)\n")

    while True:
        q = input("You: ")

        if q.lower() in ["exit", "quit"]:
            print("👋 Goodbye!")
            break

        answer = generate_answer(q)
        print("\nAssistant:\n", answer, "\n")