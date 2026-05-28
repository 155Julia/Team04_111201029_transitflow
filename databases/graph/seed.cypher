// ============================================================
//  TransitFlow — Neo4j Graph Schema
//  Seeding is performed by: python skeleton/seed_neo4j.py
//  This file documents the graph schema and provides
//  constraint definitions that are safe to run directly
//  in Neo4j Browser.
// ============================================================

// ── Constraints (idempotent) ─────────────────────────────────────────────────

CREATE CONSTRAINT IF NOT EXISTS FOR (m:MetroStation)
    REQUIRE m.station_id IS UNIQUE;

CREATE CONSTRAINT IF NOT EXISTS FOR (r:NationalRailStation)
    REQUIRE r.rail_station_id IS UNIQUE;

// ── Node labels and properties ───────────────────────────────────────────────
//
//  :MetroStation
//      station_id      String  e.g. "MS01"   (unique key)
//      name            String  e.g. "Central Square"
//      lines           List    e.g. ["M1", "M2"]
//
//  :NationalRailStation
//      rail_station_id String  e.g. "NR01"   (unique key)
//      name            String  e.g. "Central Station"
//      lines           List    e.g. ["NR1", "NR2"]

// ── Relationship types and properties ────────────────────────────────────────
//
//  (:MetroStation)-[:METRO_LINK {line, travel_time_min}]->(:MetroStation)
//      line            String  e.g. "M1"
//      travel_time_min Integer minutes between adjacent stations
//
//  (:NationalRailStation)-[:RAIL_LINK {line, travel_time_min}]->(:NationalRailStation)
//      line            String  e.g. "NR1"
//      travel_time_min Integer minutes between adjacent stations
//
//  (:MetroStation)-[:INTERCHANGE_TO]->(:NationalRailStation)  (and reverse)
//      No properties — interchange transfer time is treated as 5 min in queries
//
// ── Cross-network interchange stations ───────────────────────────────────────
//
//  MS01 (Central Square)  <-> NR01 (Central Station)
//  MS07 (Old Town)        <-> NR03 (Old Town Junction)
//  MS15 (Ferndale)        <-> NR07 (Ferndale Halt)
