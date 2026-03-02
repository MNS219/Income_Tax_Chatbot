from neo4j import GraphDatabase

driver = GraphDatabase.driver(
    "bolt://localhost:7687",
    auth=("neo4j", "password123")  # change this if needed
)


def expand_with_kg(section):
    with driver.session() as session:
        result = session.run("""
            MATCH (s:Section {name: $section})
            OPTIONAL MATCH (s)-[:HAS_ELIGIBILITY]->(e:Eligibility)
            OPTIONAL MATCH (s)-[:HAS_CONDITION]->(c:Condition)
            OPTIONAL MATCH (s)-[:HAS_EXCEPTION]->(ex:Exception)
            OPTIONAL MATCH (s)-[:HAS_INVESTMENT]->(i:Investment)

            RETURN 
                collect(DISTINCT e.name) AS eligibility,
                collect(DISTINCT c.name) AS conditions,
                collect(DISTINCT ex.name) AS exceptions,
                collect(DISTINCT i.name) AS investments
        """, section=section)

        record = result.single()

        if not record:
            return []

        output = []

        for key in ["eligibility", "conditions", "exceptions", "investments"]:
            values = record[key]

            if values:
                output.extend([str(v) for v in values if v])

        return output