import pdfplumber
import re
import json
import requests
import time
from typing import List, Any
from pydantic import BaseModel, field_validator
from tqdm import tqdm

# -------------------------------
# CONFIG
# -------------------------------
OLLAMA_MODEL = "llama3.1:8b"
OUTPUT_FILE = "final_output_parser.json"
DEBUG_RAW = False
MAX_RETRIES = 3
CHUNK_SIZE = 8000


# -------------------------------
# RELEVANCE FILTER
# -------------------------------
def is_relevant(text):
    keywords = [
        "income", "tax", "deduction", "assessee",
        "assessment", "return", "exemption", "rebate",
        "surcharge", "penalty", "interest", "relief",
        "resident", "non-resident", "salary", "capital"
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
    description: str = ""
    raw_text: str = ""   # ✅ NEW (for RAG grounding)

    amounts: List[str] = []
    percentages: List[str] = []
    eligibility: List[Any] = []
    conditions: List[Any] = []
    exceptions: List[Any] = []
    investments: List[Any] = []
    limits: List[Any] = []

    @field_validator(
        "eligibility", "conditions", "exceptions", "investments", "limits",
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

            if any(x in low for x in [
                "inserted by", "appendix", "w.e.f",
                "finance act", "omitted by",
                "substituted by", "amended by",
                "act no"
            ]):
                continue

            if len(item.split()) < 2:
                if low not in ["individual", "huf", "company", "firm", "resident", "non-resident"]:
                    continue

            if re.fullmatch(r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4}", item):
                continue

            item = re.sub(r"\s+", " ", item)

            if len(item) > 300:
                continue

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
# SECTION SPLIT — FIXED
# -------------------------------
def split_into_sections(text):
    pattern = r"(?:^|\n)(\d{1,3}[A-Z]{0,4})\.\s"
    matches = list(re.finditer(pattern, text, re.MULTILINE))
    sections = []
    seen = set()

    for i in range(len(matches)):
        section_num = matches[i].group(1)

        # ✅ FIX: correct boundary
        start = matches[i].end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)

        content = text[start:end].strip()

        if len(content.split()) < 20:
            continue

        section_name = f"Section {section_num}"

        if section_name in seen:
            continue
        seen.add(section_name)

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
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except:
                pass
        return {}


# -------------------------------
# LLM EXTRACTION
# -------------------------------
def llm_extract(section_name, text):

    prompt = f"""Extract structured information from this Indian Income Tax section.

Return ONLY JSON:
{{
  "description": "",
  "eligibility": [],
  "conditions": [],
  "exceptions": [],
  "investments": [],
  "limits": []
}}

Guidelines:
- description: one clear sentence
- eligibility = WHO (person types)
- conditions = WHEN rule applies
- exceptions = when rule does NOT apply
- limits = monetary caps

SECTION: {section_name}
TEXT:
{text[:CHUNK_SIZE]}
"""

    for _ in range(MAX_RETRIES):
        try:
            res = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
                timeout=120
            )

            raw = res.json().get("response", "").strip()
            raw = raw.replace("```json", "").replace("```", "").strip()

            parsed = safe_parse(raw)

            if parsed.get("description"):
                return parsed

        except:
            pass

    return {}


# -------------------------------
# SEMANTIC FIX
# -------------------------------
def semantic_fix(data):
    cond = []
    exc = data.get("exceptions", [])
    limits = data.get("limits", [])

    for c in data.get("conditions", []):
        low = c.lower()

        if re.search(r"rs\.|rupees|\d+%", low):
            limits.append(c)
        elif "not" in low or "excluded" in low:
            exc.append(c)
        else:
            cond.append(c)

    # ✅ FIX: move wrong eligibility → conditions
    new_elig = []
    for e in data.get("eligibility", []):
        low = e.lower()

        if any(x in low for x in ["if", "where", "case", "when", "income", "business"]):
            cond.append(e)
        else:
            new_elig.append(e)

    data["eligibility"] = new_elig
    data["conditions"] = cond
    data["exceptions"] = exc
    data["limits"] = dedupe(limits)

    return data


# -------------------------------
# PROCESS SECTION
# -------------------------------
def process_section(section):
    if not is_relevant(section["content"]):
        if len(section["content"]) < 200:
            return None

    regex_data = regex_extract(section["content"])
    llm_data = llm_extract(section["section"], section["content"])

    merged = {
        "section": section["section"],
        "description": llm_data.get("description", ""),

        # ✅ NEW: grounding for RAG
        "raw_text": section["content"][:1000],

        "amounts": regex_data["amounts"],
        "percentages": regex_data["percentages"],
        "eligibility": llm_data.get("eligibility", []),
        "conditions": llm_data.get("conditions", []),
        "exceptions": llm_data.get("exceptions", []),
        "investments": llm_data.get("investments", []),
        "limits": llm_data.get("limits", [])
    }

    validated = TaxSection(**merged).model_dump()
    return semantic_fix(validated)


# -------------------------------
# MAIN PIPELINE
# -------------------------------
def run_pipeline(pdf_path):
    print("Extracting PDF...")
    text = extract_pdf_text(pdf_path)

    print("Splitting sections...")
    sections = split_into_sections(text)
    print(f"✅ Total sections detected: {len(sections)}")

    results = []

    start_time = time.time()

    with tqdm(total=len(sections), desc="Processing") as pbar:
        for i, sec in enumerate(sections):

            processed = process_section(sec)

            if processed:
                results.append(processed)

                with open(OUTPUT_FILE, "w") as f:
                    json.dump(results, f, indent=4)

            pbar.update(1)

            elapsed = time.time() - start_time
            speed = (i + 1) / elapsed if elapsed > 0 else 0
            remaining = (len(sections) - (i + 1)) / speed if speed > 0 else 0

            pbar.set_postfix({
                "sec/s": f"{speed:.2f}",
                "ETA(min)": f"{remaining/60:.1f}"
            })

    print("\n✅ DONE — FULL DATASET READY")
    print(f"Total sections processed: {len(results)}")


# -------------------------------
# RUN
# -------------------------------
if __name__ == "__main__":
    run_pipeline("income-tax.pdf")