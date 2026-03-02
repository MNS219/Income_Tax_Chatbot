import pdfplumber
import re
import json
import requests
import time
from typing import List, Any
from pydantic import BaseModel, field_validator
from tqdm import tqdm   # ✅ NEW

# -------------------------------
# CONFIG
# -------------------------------
OLLAMA_MODEL = "llama3.1:8b"
OUTPUT_FILE = "final_output_parser2.json"
DEBUG_RAW = False   # 🔥 toggle raw LLM output


# -------------------------------
# RELEVANCE FILTER
# -------------------------------
def is_relevant(text):
    keywords = [
        "income", "tax", "deduction",
        "assessee", "assessment", "return"
    ]
    text = text.lower()
    return any(k in text for k in keywords)


# -------------------------------
# TEXT FLATTENER
# -------------------------------
def extract_text(obj):
    results = []

    if isinstance(obj, str):
        results.append(obj)

    elif isinstance(obj, list):
        for item in obj:
            results.extend(extract_text(item))

    elif isinstance(obj, dict):
        for key in ["description", "condition", "text", "name"]:
            if key in obj:
                results.append(str(obj[key]))

        for v in obj.values():
            results.extend(extract_text(v))

    return results

# -------------------------------
# DEDUPE
# -------------------------------
def dedupe(lst):
    seen = set()
    result = []

    for item in lst:
        key = item.lower().strip()
        if key not in seen:
            seen.add(key)
            result.append(item)

    return result


# -------------------------------
# PYDANTIC MODEL
# -------------------------------
class TaxSection(BaseModel):
    section: str
    amounts: List[str] = []
    percentages: List[str] = []
    eligibility: List[Any] = []
    conditions: List[Any] = []
    exceptions: List[Any] = []
    investments: List[Any] = []

    @field_validator(
        "eligibility", "conditions", "exceptions", "investments",
        mode="before"
    )
    def clean(cls, v):
        if not isinstance(v, list):
            return []

        flat = []
        for item in v:
            flat.extend(extract_text(item))

        cleaned = []

        for item in flat:
            item = str(item).strip()
            low = item.lower()

            if not item:
                continue

            # ❌ garbage removal
            if any(x in low for x in [
                "inserted by", "appendix", "w.e.f",
                "finance act", "omitted by",
                "substituted by", "amended by",
                "act no"
            ]):
                continue

            if len(item.split()) < 3:
                continue

            if re.fullmatch(r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4}", item):
                continue

            item = re.sub(r"\s+", " ", item)

            if len(item) > 200:
                item = item[:200]

            cleaned.append(item)

        return dedupe(cleaned)


# -------------------------------
# PDF EXTRACTION
# -------------------------------
def extract_pdf_text(pdf_path):
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"
    return text


# -------------------------------
# SECTION SPLIT
# -------------------------------
def split_into_sections(text):
    pattern = r"\n(\d+[A-Z]{0,3})\.\s"

    matches = list(re.finditer(pattern, text))
    sections = []
    seen = set()

    for i in range(len(matches)):
        section_num = matches[i].group(1)

        if not re.fullmatch(r"\d{1,3}[A-Z]{0,3}", section_num):
            continue

        section_name = f"Section {section_num}"

        if section_name in seen:
            continue
        seen.add(section_name)

        start = matches[i].start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)

        content = text[start:end].strip()

        sections.append({
            "section": section_name,
            "content": content
        })

    return sections


# -------------------------------
# REGEX EXTRACTION
# -------------------------------
def regex_extract(text):
    return {
        "amounts": re.findall(r"₹[\d,]+", text),
        "percentages": re.findall(r"\d+%", text)
    }


# -------------------------------
# SAFE PARSE
# -------------------------------
def safe_parse(raw):
    try:
        return json.loads(raw)
    except:
        return {}


# -------------------------------
# LLM EXTRACTION
# -------------------------------
def llm_extract(text):
    prompt = f"""
Extract structured info from Income Tax section.

Return JSON:
{{
  "eligibility": [],
  "conditions": [],
  "exceptions": [],
  "investments": []
}}

Rules:
- Extract meaningful legal phrases
- Keep phrases short
- No explanations
- Return ONLY JSON

TEXT:
{text[:3500]}
"""

    try:
        res = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False
            }
        )

        raw = res.json().get("response", "").strip()

        if DEBUG_RAW:
            print("\n--- RAW OUTPUT ---\n", raw)

        raw = raw.replace("```json", "").replace("```", "").strip()

        return safe_parse(raw)

    except Exception as e:
        print("LLM error:", e)
        return {}


# -------------------------------
# SEMANTIC FIX
# -------------------------------
def semantic_fix(data):
    cond = []
    exc = data.get("exceptions", [])

    for c in data.get("conditions", []):
        if any(x in c.lower() for x in ["not", "excluded", "shall not"]):
            exc.append(c)
        else:
            cond.append(c)

    data["conditions"] = cond
    data["exceptions"] = exc

    return data


# -------------------------------
# PROCESS SECTION
# -------------------------------
def process_section(section):
    if not is_relevant(section["content"]):
        return None

    regex_data = regex_extract(section["content"])
    llm_data = llm_extract(section["content"])

    merged = {
        "section": section["section"],
        "amounts": regex_data["amounts"],
        "percentages": regex_data["percentages"],
        "eligibility": llm_data.get("eligibility", []),
        "conditions": llm_data.get("conditions", []),
        "exceptions": llm_data.get("exceptions", []),
        "investments": llm_data.get("investments", [])
    }

    validated = TaxSection(**merged).model_dump()
    final = semantic_fix(validated)

    return final


# -------------------------------
# MAIN PIPELINE (WITH PROGRESS BAR)
# -------------------------------
def run_pipeline(pdf_path):
    print("Extracting PDF...")
    text = extract_pdf_text(pdf_path)

    print("Splitting sections...")
    sections = split_into_sections(text)

    print(f"✅ Total sections detected: {len(sections)}")

    try:
        with open(OUTPUT_FILE, "r") as f:
            results = json.load(f)
    except:
        results = []

    processed_sections = {r["section"] for r in results}

    start_time = time.time()

    with tqdm(total=len(sections), desc="Processing Sections") as pbar:
        for i, sec in enumerate(sections):

            if sec["section"] in processed_sections:
                pbar.update(1)
                continue

            processed = process_section(sec)

            if processed:
                results.append(processed)

                with open(OUTPUT_FILE, "w") as f:
                    json.dump(results, f, indent=4)

            pbar.update(1)

            # 🔥 dynamic speed + ETA
            elapsed = time.time() - start_time
            speed = (i + 1) / elapsed if elapsed > 0 else 0
            remaining = (len(sections) - (i + 1)) / speed if speed > 0 else 0

            pbar.set_postfix({
                "sec/s": f"{speed:.2f}",
                "ETA(min)": f"{remaining/60:.1f}"
            })

    print("\n✅ DONE — FULL DATASET READY")


# -------------------------------
# RUN
# -------------------------------
if __name__ == "__main__":
    run_pipeline("income-tax.pdf")