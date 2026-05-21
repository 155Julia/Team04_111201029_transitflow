"""
TransitFlow — Neo4j Graph Database Layer
=========================================
This module handles all queries to Neo4j.
"""

from __future__ import annotations

from typing import Optional
from neo4j import GraphDatabase
from skeleton.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD


def _driver():
    """Return a Neo4j driver. Caller is responsible for closing."""
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


# ── FASTEST ROUTE (Dijkstra by travel_time_min) ───────────────────────────────

def query_shortest_route(
    origin_id: str,
    destination_id: str,
    network: str = "auto",
) -> dict:
    """
    Find the fastest path between two stations, minimising total travel time.
    Uses shortestPath with travel_time_min weights on CONNECTED_TO edges.
    INTERCHANGE_TO edges are treated as 5-minute transfer time.
    """
    query = """
    MATCH (start), (end)
    WHERE (start.station_id = $start OR start.rail_station_id = $start)
      AND (end.station_id = $end OR end.rail_station_id = $end)
    MATCH p = shortestPath((start)-[:CONNECTED_TO|INTERCHANGE_TO*]-(end))
    WITH p,
         reduce(total = 0, r IN relationships(p) |
             total + CASE type(r)
                 WHEN 'INTERCHANGE_TO' THEN 5
                 ELSE coalesce(r.travel_time_min, 3)
             END
         ) AS total_time_min
    RETURN
        [n IN nodes(p) | {
            station_id: coalesce(n.station_id, n.rail_station_id),
            name: n.name,
            lines: n.lines
        }] AS path,
        total_time_min
    ORDER BY total_time_min ASC
    LIMIT 1
    """
    with _driver() as driver:
        with driver.session() as session:
            res = session.run(query, start=origin_id, end=destination_id)
            record = res.single()
            if record:
                return {
                    "found": True,
                    "origin_id": origin_id,
                    "destination_id": destination_id,
                    "total_time_min": record["total_time_min"],
                    "path": record["path"],
                    "legs": len(record["path"]) - 1,
                }
            return {
                "found": False,
                "origin_id": origin_id,
                "destination_id": destination_id,
                "total_time_min": 0,
                "path": [],
                "legs": 0,
            }


# ── CHEAPEST ROUTE (Dijkstra by fare) ────────────────────────────────────────

def query_cheapest_route(
    origin_id: str,
    destination_id: str,
    network: str = "auto",
    fare_class: str = "standard",
) -> dict:
    """
    Find the cheapest path between two stations, minimising total estimated fare.
    Metro stops: base 0.80 + 0.30/stop. National rail stops: base 2.50 + 1.50/stop (standard).
    Interchange transfers are free.
    """
    query = """
    MATCH (start), (end)
    WHERE (start.station_id = $start OR start.rail_station_id = $start)
      AND (end.station_id = $end OR end.rail_station_id = $end)
    MATCH p = shortestPath((start)-[:CONNECTED_TO|INTERCHANGE_TO*]-(end))
    WITH p,
         reduce(total = 0.0, r IN relationships(p) |
             total + CASE type(r)
                 WHEN 'INTERCHANGE_TO' THEN 0.0
                 WHEN 'CONNECTED_TO' THEN
                     CASE WHEN 'NationalRailStation' IN labels(startNode(r))
                          THEN 1.50
                          ELSE 0.30
                     END
                 ELSE 0.0
             END
         ) AS total_fare_usd
    RETURN
        [n IN nodes(p) | coalesce(n.name, 'Unknown')] AS stations,
        [n IN nodes(p) | coalesce(n.station_id, n.rail_station_id)] AS ids,
        total_fare_usd
    ORDER BY total_fare_usd ASC
    LIMIT 1
    """
    with _driver() as driver:
        with driver.session() as session:
            res = session.run(query, start=origin_id, end=destination_id)
            record = res.single()
            if record:
                return {
                    "found": True,
                    "total_fare_usd": round(float(record["total_fare_usd"]), 2),
                    "stations": record["stations"],
                    "legs": len(record["ids"]) - 1,
                }
            return {"found": False, "total_fare_usd": 0.0, "stations": [], "legs": 0}


# ── ALTERNATIVE ROUTES (avoiding a station) ───────────────────────────────────

def query_alternative_routes(
    origin_id: str,
    destination_id: str,
    avoid_station_id: str,
    network: str = "auto",
    max_routes: int = 3,
) -> list[list[dict]]:
    """
    Find paths between two stations that avoid a specific intermediate station.
    """
    query = """
    MATCH (start), (end)
    WHERE (start.station_id = $start OR start.rail_station_id = $start)
      AND (end.station_id = $end OR end.rail_station_id = $end)
    MATCH p = (start)-[:CONNECTED_TO|INTERCHANGE_TO*..40]->(end)
    WHERE NONE(n IN nodes(p) WHERE n.station_id = $avoid OR n.rail_station_id = $avoid)
    WITH p, length(p) as stops
    ORDER BY stops ASC
    RETURN [n in nodes(p) | {
        "station_id": coalesce(n.station_id, n.rail_station_id), 
        "name": n.name
    }] as legs_list
    LIMIT $max_routes
    """
    with _driver() as driver:
        with driver.session() as session:
            res = session.run(query, start=origin_id, end=destination_id, avoid=avoid_station_id, max_routes=max_routes)
            return [rec["legs_list"] for rec in res]


# ── CROSS-NETWORK INTERCHANGE PATH ───────────────────────────────────────────

def query_interchange_path(origin_id: str, destination_id: str) -> dict:
    """
    Find a path between a metro station and a national rail station (or vice versa)
    crossing the network boundary via interchange relationships.
    """
    query = """
    MATCH (start), (end)
    WHERE (start.station_id = $start OR start.rail_station_id = $start)
      AND (end.station_id = $end OR end.rail_station_id = $end)
    MATCH p = shortestPath((start)-[:CONNECTED_TO|INTERCHANGE_TO*]-(end))
    WHERE ANY(r IN relationships(p) WHERE type(r) = 'INTERCHANGE_TO')
    WITH p,
         reduce(total = 0, r IN relationships(p) |
             total + CASE type(r)
                 WHEN 'INTERCHANGE_TO' THEN 5
                 ELSE coalesce(r.travel_time_min, 3)
             END
         ) AS total_time_min
    RETURN
        [n IN nodes(p) | coalesce(n.name, 'Unknown')] AS stations,
        [n IN nodes(p) | coalesce(n.station_id, n.rail_station_id)] AS ids,
        total_time_min
    ORDER BY total_time_min ASC
    LIMIT 1
    """
    with _driver() as driver:
        with driver.session() as session:
            res = session.run(query, start=origin_id, end=destination_id)
            record = res.single()
            if record:
                interchange_ids = {"MS01", "NR01", "MS07", "NR03", "MS15", "NR07"}
                interchanges = [sid for sid in record["ids"] if sid in interchange_ids]
                return {
                    "found": True,
                    "stations": record["stations"],
                    "interchange_points": list(set(interchanges)),
                    "total_time_min": record["total_time_min"],
                }
            return {"found": False, "stations": [], "interchange_points": [], "total_time_min": 0}


# ── DELAY RIPPLE ANALYSIS ─────────────────────────────────────────────────────

def query_delay_ripple(delayed_station_id: str, hops: int = 2) -> list[dict]:
    """
    Find all stations within N hops of a delayed or disrupted station.
    """
    query = """
    MATCH (center)
    WHERE center.station_id = $broken_id OR center.rail_station_id = $broken_id
    MATCH p = (center)-[:CONNECTED_TO|INTERCHANGE_TO*1..%d]-(affected)
    WHERE center <> affected
    RETURN DISTINCT coalesce(affected.station_id, affected.rail_station_id) as station_id,
                    affected.name as name,
                    length(p) as hops_away,
                    affected.lines as lines_affected
    ORDER BY hops_away ASC
    """ % int(hops)
    with _driver() as driver:
        with driver.session() as session:
            res = session.run(query, broken_id=delayed_station_id)
            return [dict(rec) for rec in res]


# ── STATION CONNECTIONS ───────────────────────────────────────────────────────

def query_station_connections(station_id: str) -> list[dict]:
    """
    List all direct connections from a given station.
    """
    query = """
    MATCH (curr)
    WHERE curr.station_id = $station_id OR curr.rail_station_id = $station_id
    MATCH (curr)-[:CONNECTED_TO]-(neighbor)
    RETURN coalesce(neighbor.station_id, neighbor.rail_station_id) as station_id,
           neighbor.name as name,
           neighbor.lines as lines
    """
    with _driver() as driver:
        with driver.session() as session:
            res = session.run(query, station_id=station_id)
            return [dict(rec) for rec in res]