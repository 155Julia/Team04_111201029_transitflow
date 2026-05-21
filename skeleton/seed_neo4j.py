import json
from neo4j import GraphDatabase

# ============================================================
# 對齊 docker-compose.yml 認定的黃金連線參數
# ============================================================
URI = "bolt://localhost:7688"      # 嚴格對齊映射埠號 7688
AUTH = ("neo4j", "transitflow")    # 嚴格對齊真實密碼

def seed_neo4j():
    print("🌐 正在連線至 Neo4j 圖形資料庫...")
    driver = GraphDatabase.driver(URI, auth=AUTH)
    
    # 1. 讀取車站原始 JSON 資料
    try:
        with open("train-mock-data/metro_stations.json", "r", encoding="utf-8") as f:
            metro_stations = json.load(f)
        with open("train-mock-data/national_rail_stations.json", "r", encoding="utf-8") as f:
            rail_stations = json.load(f)
    except FileNotFoundError as e:
        print(f"❌ 找不到 JSON 檔案，請確認是在專案根目錄下執行本腳本！錯誤: {e}")
        return

    with driver.session() as session:
        # 2. 清空舊圖表，確保每次重跑都是乾淨的
        session.run("MATCH (n) DETACH DELETE n;")
        print("🧹 舊的 Neo4j 車站拓撲資料已徹底清空")

        # 3. 建立 [地鐵站] 節點 (:MetroStation)，用 MERGE 避免重跑時產生重複節點
        for station in metro_stations:
            session.run("""
                MERGE (m:MetroStation {station_id: $station_id})
                SET m.name = $name, m.lines = $lines
            """, station_id=station["station_id"], name=station["name"], lines=station["lines"])
        print(f"🚉 [地鐵] 已成功建立 {len(metro_stations)} 個車站節點 (:MetroStation)")

        # 4. 建立 [國鐵站] 節點 (:NationalRailStation)，用 MERGE 避免重跑時產生重複節點
        for station in rail_stations:
            session.run("""
                MERGE (r:NationalRailStation {rail_station_id: $station_id})
                SET r.name = $name, r.lines = $lines
            """, station_id=station["station_id"], name=station["name"], lines=station["lines"])
        print(f"🚂 [國鐵] 已成功建立 {len(rail_stations)} 個車站節點 (:NationalRailStation)")

        # 5. 建立 [地鐵線相鄰路軌] 雙向連線關係 [:CONNECTED_TO] (metro links)
        # adjacent_stations 是 dict 陣列，需取出 station_id 和 travel_time_min
        for station in metro_stations:
            for adj in station.get("adjacent_stations", []):
                adj_id = adj["station_id"]
                travel_time = adj.get("travel_time_min", 3)
                line = adj.get("line", "")
                session.run("""
                    MATCH (a:MetroStation {station_id: $curr_id}), (b:MetroStation {station_id: $adj_id})
                    MERGE (a)-[r:CONNECTED_TO {line: $line}]->(b)
                    SET r.travel_time_min = $travel_time
                    MERGE (b)-[r2:CONNECTED_TO {line: $line}]->(a)
                    SET r2.travel_time_min = $travel_time
                """, curr_id=station["station_id"], adj_id=adj_id,
                     travel_time=travel_time, line=line)
        print("🛤️ [地鐵線] (metro links) 建置雙向連線完畢（含 travel_time_min）！")

        # 6. 建立 [國鐵線相鄰路軌] 雙向連線關係 [:CONNECTED_TO] (rail links)
        # 從 national_rail_stations.json 的 adjacent_stations 讀取，同樣是 dict 陣列
        for station in rail_stations:
            for adj in station.get("adjacent_stations", []):
                adj_id = adj["station_id"]
                travel_time = adj.get("travel_time_min", 15)
                line = adj.get("line", "")
                session.run("""
                    MATCH (a:NationalRailStation {rail_station_id: $curr}),
                          (b:NationalRailStation {rail_station_id: $next})
                    MERGE (a)-[r:CONNECTED_TO {line: $line}]->(b)
                    SET r.travel_time_min = $travel_time
                    MERGE (b)-[r2:CONNECTED_TO {line: $line}]->(a)
                    SET r2.travel_time_min = $travel_time
                """, curr=station["station_id"], next=adj_id,
                     travel_time=travel_time, line=line)
        print("🛣️ [國鐵線] (rail links) 建置雙向連線完畢（含 travel_time_min）！")

        # 7. 建立 [3 大跨系統車站內轉乘地下道] 雙向邊關係 [:INTERCHANGE_TO] (interchange links)
        interchanges = [
            ("MS01", "NR01"),  # Central Square
            ("MS07", "NR03"),  # Old Town
            ("MS15", "NR07")   # Ferndale
        ]
        for m_id, r_id in interchanges:
            session.run("""
                MATCH (m:MetroStation {station_id: $m_id}), (r:NationalRailStation {rail_station_id: $r_id})
                MERGE (m)-[:INTERCHANGE_TO]->(r)
                MERGE (r)-[:INTERCHANGE_TO]->(m)
            """, m_id=m_id, r_id=r_id)
        print("🔗 3 大天王級「地鐵 ↔ 國鐵」換乘地下步道 (interchange links) 串接完畢！")

    driver.close()
    print("🎉 [Task 2] Neo4j 全系統雙路網拓撲圖圖形灌錄大成功！")

if __name__ == "__main__":
    seed_neo4j()