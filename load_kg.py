import os
from neo4j import GraphDatabase
import json

URI = "bolt://localhost:7687"
USERNAME = "neo4j"
PASSWORD = "password123"   
JSON_FILE = "final_output_parser.json"

driver = GraphDatabase.driver(URI, auth=(USERNAME, PASSWORD))


def create_kg(tx, section_data):
    section_name = section_data["section"]
    description  = section_data.get("description", "")
    raw_text     = section_data.get("raw_text", "")

    # Store description and raw_text on the Section node itself
    tx.run("""
        MERGE (s:Section {name: $section})
        SET s.description = $description,
            s.raw_text    = $raw_text
    """, section=section_name, description=description, raw_text=raw_text)

    def create_nodes(items, label, rel):
        for item in items:
            if not item or not str(item).strip():
                continue
            tx.run(f"""
                MERGE (n:{label} {{name: $name}})
                WITH n
                MATCH (s:Section {{name: $section}})
                MERGE (s)-[:{rel}]->(n)
            """, name=str(item).strip(), section=section_name)

    create_nodes(section_data.get("eligibility",  []), "Eligibility", "HAS_ELIGIBILITY")
    create_nodes(section_data.get("conditions",   []), "Condition",   "HAS_CONDITION")
    create_nodes(section_data.get("exceptions",   []), "Exception",   "HAS_EXCEPTION")
    create_nodes(section_data.get("investments",  []), "Investment",  "HAS_INVESTMENT")
    create_nodes(section_data.get("limits",       []), "Limit",       "HAS_LIMIT")


def load_data():
    with open(JSON_FILE, "r") as f:
        data = json.load(f)

    print(f"Total sections to load: {len(data)}")
    failed = []

    with driver.session() as session:
        for i, section in enumerate(data):
            try:
                print(f"Inserting {section['section']} ({i+1}/{len(data)})")
                session.execute_write(create_kg, section)
            except Exception as e:
                print(f"  Failed: {section['section']} — {e}")
                failed.append(section["section"])

    driver.close()
    print(f"\nKG successfully created!")
    if failed:
        print(f"Failed sections ({len(failed)}): {failed}")


if __name__ == "__main__":
    load_data()