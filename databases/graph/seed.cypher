// Deprecated: seeding is now done via skeleton/seed_neo4j.py
// which loads data directly from train-mock-data/ JSON files.
//
// If you prefer Cypher-file seeding, implement your graph schema here.
// Run with: python skeleton/seed_neo4j.py (or via the Neo4j Browser)
CREATE CONSTRAINT IF NOT EXISTS FOR (m:MetroStation) REQUIRE m.station_id IS UNIQUE;

CREATE CONSTRAINT IF NOT EXISTS FOR (r:RailStation) REQUIRE r.rail_station_id IS UNIQUE;