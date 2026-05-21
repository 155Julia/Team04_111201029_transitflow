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

        # 3. 建立 [地鐵站] 節點 (:MetroStation)
        for station in metro_stations:
            session.run("""
                CREATE (m:MetroStation {
                    station_id: $station_id,
                    name: $name,
                    lines: $lines
                })
            """, station_id=station["station_id"], name=station["name"], lines=station["lines"])
        print(f"🚉 [地鐵] 已成功建立 {len(metro_stations)} 個車站節點 (:MetroStation)")

        # 4. 建立 [國鐵站] 節點 (:NationalRailStation)
        for station in rail_stations:
            session.run("""
                CREATE (r:NationalRailStation {
                    rail_station_id: $station_id,
                    name: $name,
                    lines: $lines
                })
            """, station_id=station["station_id"], name=station["name"], lines=station["lines"])
        print(f"🚂 [國鐵] 已成功建立 {len(rail_stations)} 個車站節點 (:NationalRailStation)")

        # 5. 建立 [地鐵線相鄰路軌] 雙向連線關係 [:CONNECTED_TO] (metro links)
        for station in metro_stations:
            for adj_id in station.get("adjacent_stations", []):
                session.run("""
                    MATCH (a:MetroStation {station_id: $curr_id}), (b:MetroStation {station_id: $adj_id})
                    MERGE (a)-[:CONNECTED_TO]->(b)
                    MERGE (b)-[:CONNECTED_TO]->(a)
                """, curr_id=station["station_id"], adj_id=adj_id)
        print("Tracks 🛤️ [地鐵線] (metro links) 建置雙向連線完畢！")

        # 6. 建立 [國鐵線相鄰路軌] 雙向連線關係 [:CONNECTED_TO] (rail links)
        # 依據資料摘要：NR1 線為 NR01-NR05，NR2 線為 NR01 與 NR06-NR10
        nr1_route = ["NR01", "NR02", "NR03", "NR04", "NR05"]
        nr2_route = ["NR01", "NR06", "NR07", "NR08", "NR09", "NR10"]

        # 串連 NR1 鐵軌
        for i in range(len(nr1_route) - 1):
            session.run("""
                MATCH (a:NationalRailStation {rail_station_id: $curr}), (b:NationalRailStation {rail_station_id: $next})
                MERGE (a)-[:CONNECTED_TO]->(b)
                MERGE (b)-[:CONNECTED_TO]->(a)
            """, curr=nr1_route[i], next=nr1_route[i+1])

        # 串連 NR2 鐵軌
        for i in range(len(nr2_route) - 1):
            session.run("""
                MATCH (a:NationalRailStation {rail_station_id: $curr}), (b:NationalRailStation {rail_station_id: $next})
                MERGE (a)-[:CONNECTED_TO]->(b)
                MERGE (b)-[:CONNECTED_TO]->(a)
            """, curr=nr2_route[i], next=nr2_route[i+1])
        print("Tracks 🛣️ [國鐵線] (rail links) 建置雙向連線完畢！")

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