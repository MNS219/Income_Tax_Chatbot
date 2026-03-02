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
    match = re.search(r"section\s*(\d+[a-zA-Z]*)", query.lower())
    if match:
        section = match.group(1).upper()   # 🔥 FORCE CORRECT FORMAT
        return f"Section {section}"
    return None


# -------------------------------
# BUILD HISTORY CONTEXT
# -------------------------------
def build_history_context():
    history_text = ""

    for q, a in chat_history[-3:]:
        history_text += f"\nUser: {q}\nAssistant: {a}\n"

    return history_text


# -------------------------------
# GENERATE ANSWER
# -------------------------------
def generate_answer(query):
    section_name = extract_section(query)

    context = ""

    # 🔥 DIRECT SECTION MATCH
    if section_name:
        print(f"✅ Using direct section: {section_name}")

        docs = retrieve(section_name)

        # exact match
        docs = [
            d for d in docs
            if d["section"].strip().lower() == section_name.strip().lower()
        ]

    else:
        docs = retrieve(query)

    if not docs:
        return "Not found in data"

    for doc in docs:
        context += f"\n{doc['section']}:\n{doc['text']}\n"

        kg_data = expand_with_kg(doc["section"])

        if kg_data:
            context += "\n".join(kg_data) + "\n"

    history_context = build_history_context()

    prompt = f"""
You are a tax assistant.

Conversation history:
{history_context}

Context:
{context}

Question:
{query}

Instructions:
- Use conversation history if relevant
- Group information properly (Eligibility, Investments, Limits)
- Do NOT mix categories
- Clean up wording
- Remove duplicates
- Keep answer simple
- Do NOT add outside knowledge
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

    # save memory
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