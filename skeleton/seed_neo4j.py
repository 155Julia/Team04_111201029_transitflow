import json
from neo4j import GraphDatabase

# ============================================================
# Connection parameters — aligned with docker-compose.yml
# ============================================================
URI = "bolt://localhost:7688"
AUTH = ("neo4j", "transitflow")


def seed_neo4j():
    print("Connecting to Neo4j...")
    driver = GraphDatabase.driver(URI, auth=AUTH)

    try:
        with open("train-mock-data/metro_stations.json", "r", encoding="utf-8") as f:
            metro_stations = json.load(f)
        with open("train-mock-data/national_rail_stations.json", "r", encoding="utf-8") as f:
            rail_stations = json.load(f)
    except FileNotFoundError as e:
        print(f"ERROR: JSON file not found. Run from project root. {e}")
        return

    with driver.session() as session:

        # ── Constraints (idempotent) ──────────────────────────────────────────
        session.run(
            "CREATE CONSTRAINT IF NOT EXISTS FOR (m:MetroStation) "
            "REQUIRE m.station_id IS UNIQUE"
        )
        session.run(
            "CREATE CONSTRAINT IF NOT EXISTS FOR (r:NationalRailStation) "
            "REQUIRE r.rail_station_id IS UNIQUE"
        )
        session.run(
            "CREATE CONSTRAINT IF NOT EXISTS FOR (r:NationalRailStation) "
            "REQUIRE r.station_id IS UNIQUE"
        )

        # ── MetroStation nodes ────────────────────────────────────────────────
        # MERGE ensures re-running does not create duplicate nodes
        for station in metro_stations:
            session.run(
                "MERGE (m:MetroStation {station_id: $sid}) "
                "SET m.name = $name, m.lines = $lines",
                sid=station["station_id"],
                name=station["name"],
                lines=station["lines"],
            )
        print(f"  MetroStation nodes: {len(metro_stations)}")

        # ── NationalRailStation nodes ─────────────────────────────────────────
        for station in rail_stations:
            session.run(
                "MERGE (r:NationalRailStation {rail_station_id: $sid}) "
                "SET r.station_id = $sid, r.name = $name, r.lines = $lines",
                sid=station["station_id"],
                name=station["name"],
                lines=station["lines"],
            )
        print(f"  NationalRailStation nodes: {len(rail_stations)}")

        # ── METRO_LINK relationships ──────────────────────────────────────────
        # adjacent_stations is a list of dicts with station_id, line, travel_time_min
        for station in metro_stations:
            for adj in station.get("adjacent_stations", []):
                session.run(
                    "MATCH (a:MetroStation {station_id: $from_id}) "
                    "MATCH (b:MetroStation {station_id: $to_id}) "
                    "MERGE (a)-[r:METRO_LINK {line: $line}]->(b) "
                    "SET r.travel_time_min = $time",
                    from_id=station["station_id"],
                    to_id=adj["station_id"],
                    line=adj.get("line", ""),
                    time=adj.get("travel_time_min", 3),
                )
        print("  METRO_LINK relationships created")

        # ── RAIL_LINK relationships ───────────────────────────────────────────
        for station in rail_stations:
            for adj in station.get("adjacent_stations", []):
                session.run(
                    "MATCH (a:NationalRailStation {rail_station_id: $from_id}) "
                    "MATCH (b:NationalRailStation {rail_station_id: $to_id}) "
                    "MERGE (a)-[r:RAIL_LINK {line: $line}]->(b) "
                    "SET r.travel_time_min = $time",
                    from_id=station["station_id"],
                    to_id=adj["station_id"],
                    line=adj.get("line", ""),
                    time=adj.get("travel_time_min", 15),
                )
        print("  RAIL_LINK relationships created")

        # ── INTERCHANGE_TO relationships ──────────────────────────────────────
        # Three cross-network interchange points derived from station JSON data
        interchanges = [
            ("MS01", "NR01"),  # Central Square <-> Central Station
            ("MS07", "NR03"),  # Old Town <-> Old Town Junction
            ("MS15", "NR07"),  # Ferndale <-> Ferndale Halt
        ]
        for m_id, r_id in interchanges:
            session.run(
                "MATCH (m:MetroStation {station_id: $m_id}) "
                "MATCH (r:NationalRailStation {rail_station_id: $r_id}) "
                "MERGE (m)-[:INTERCHANGE_TO]->(r) "
                "MERGE (r)-[:INTERCHANGE_TO]->(m)",
                m_id=m_id,
                r_id=r_id,
            )
        print(f"  INTERCHANGE_TO relationships: {len(interchanges)} pairs")

    driver.close()
    print("Neo4j seeding complete.")


if __name__ == "__main__":
    seed_neo4j()
