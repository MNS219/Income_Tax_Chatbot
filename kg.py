import os
from neo4j import GraphDatabase

URI = "bolt://localhost:7687"
USERNAME = "neo4j"
PASSWORD = "password123" 

driver = GraphDatabase.driver(URI, auth=(USERNAME, PASSWORD))


def expand_with_kg(section):
    """
    Returns a dict with all KG data for a section:
    {
        "description": str,
        "raw_text": str,
        "eligibility": [...],
        "conditions": [...],
        "exceptions": [...],
        "investments": [...],
        "limits": [...]
    }
    Returns empty dict if section not found.
    """
    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (s:Section {name: $section})
                OPTIONAL MATCH (s)-[:HAS_ELIGIBILITY]->(e:Eligibility)
                OPTIONAL MATCH (s)-[:HAS_CONDITION]->(c:Condition)
                OPTIONAL MATCH (s)-[:HAS_EXCEPTION]->(ex:Exception)
                OPTIONAL MATCH (s)-[:HAS_INVESTMENT]->(i:Investment)
                OPTIONAL MATCH (s)-[:HAS_LIMIT]->(l:Limit)

                RETURN
                    s.description                AS description,
                    s.raw_text                   AS raw_text,
                    collect(DISTINCT e.name)     AS eligibility,
                    collect(DISTINCT c.name)     AS conditions,
                    collect(DISTINCT ex.name)    AS exceptions,
                    collect(DISTINCT i.name)     AS investments,
                    collect(DISTINCT l.name)     AS limits
            """, section=section)

            record = result.single()

            if not record:
                return {}

            return {
                "description": record["description"] or "",
                "raw_text":    record["raw_text"]    or "",
                "eligibility": [v for v in record["eligibility"]  if v],
                "conditions":  [v for v in record["conditions"]   if v],
                "exceptions":  [v for v in record["exceptions"]   if v],
                "investments": [v for v in record["investments"]  if v],
                "limits":      [v for v in record["limits"]       if v],
            }

    except Exception as e:
        print(f"  KG query failed for {section}: {e}")
        return {}