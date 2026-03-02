from neo4j import GraphDatabase
import json

# -------------------------------
# CONFIG
# -------------------------------
URI = "bolt://localhost:7687"
USERNAME = "neo4j"
PASSWORD = "password123"   # 🔥 change this

JSON_FILE = "final_output_parser2.json"


# -------------------------------
# CONNECT
# -------------------------------
driver = GraphDatabase.driver(URI, auth=(USERNAME, PASSWORD))


# -------------------------------
# CREATE KG
# -------------------------------
def create_kg(tx, section_data):
    section_name = section_data["section"]

    # Create Section node
    tx.run("""
        MERGE (s:Section {name: $section})
    """, section=section_name)

    # Generic handler
    def create_nodes(items, label, rel):
        for item in items:
            tx.run(f"""
                MERGE (n:{label} {{text: $text}})
                WITH n
                MATCH (s:Section {{name: $section}})
                MERGE (s)-[:{rel}]->(n)
            """, text=item, section=section_name)

    create_nodes(section_data.get("eligibility", []), "Eligibility", "HAS_ELIGIBILITY")
    create_nodes(section_data.get("conditions", []), "Condition", "HAS_CONDITION")
    create_nodes(section_data.get("exceptions", []), "Exception", "HAS_EXCEPTION")
    create_nodes(section_data.get("investments", []), "Investment", "HAS_INVESTMENT")


# -------------------------------
# LOAD DATA
# -------------------------------
def load_data():
    with open(JSON_FILE, "r") as f:
        data = json.load(f)

    print(f"Total sections: {len(data)}")

    with driver.session() as session:
        for i, section in enumerate(data):
            print(f"Inserting {section['section']} ({i+1}/{len(data)})")
            session.execute_write(create_kg, section)   # ✅ FIXED

    print("\n✅ KG successfully created!")


# -------------------------------
# RUN
# -------------------------------
if __name__ == "__main__":
    load_data()