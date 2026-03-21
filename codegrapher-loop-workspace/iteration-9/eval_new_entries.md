# Eval: New Entry Points (Iteration 9) — evals 4-8

All 5 new entry points passed 1.00/1.00/0.00.

---

## Eval 4: lookup_loader.py — flowchart TB — PASS

GT nodes (8): load_all, _load_table, _load_resource_types, db_util.connect, db_util.close, _load_json_file, db_util.execute, db_util.execute_many
GT edges (9): load_all→_load_table, load_all→_load_resource_types, load_all→db_util.connect, load_all→db_util.close, _load_table→_load_json_file, _load_table→db_util.execute, _load_table→db_util.execute_many, _load_resource_types→_load_json_file, _load_resource_types→db_util.execute_many
Shared terminal: ONE db_util.execute_many (serves both _load_table and _load_resource_types).
node_recall=1.00, edge_recall=1.00, hallucination=0.00

---

## Eval 5: taxonomy_loader.py — flowchart TB — PASS

GT nodes (12): load_taxonomy, _process_category, _insert_taxonomy_node, _get_ingredient_id, _insert_mapping, _fetch_one, db_util.connect, db_util.execute, db_util.commit, db_util.close, db_util.fetch_one, db_util.fetchone
GT edges (16): load_taxonomy→_process_category, _process_category→_insert_taxonomy_node, _process_category→_get_ingredient_id, _process_category→_insert_mapping, _process_category→_process_category, load_taxonomy→db_util.connect, load_taxonomy→db_util.execute, load_taxonomy→db_util.commit, load_taxonomy→db_util.close, _insert_taxonomy_node→db_util.fetch_one, _insert_taxonomy_node→db_util.execute, _get_ingredient_id→_fetch_one, _fetch_one→db_util.fetch_one, _fetch_one→db_util.execute, _fetch_one→db_util.fetchone, _insert_mapping→db_util.execute
Shared terminals: ONE each of db_util.execute, db_util.commit, db_util.fetch_one.
node_recall=1.00, edge_recall=1.00, hallucination=0.00

---

## Eval 6: ingredients.py (Server_Side/api/routes/) — sequenceDiagram — PASS

Pattern identical to sync.py v3: db = get_database() → PostgresDatabaseUtility, graph has resolved edges.
GT actors (3): ingredients.py, db_factory.py, pg_database_utility.py
GT messages (5): get_database, execute, fetchall, fetchone, close
Two endpoints (get_master_ingredients, get_seasonality_by_zone) compressed per repeated-call-compression rule.
node_recall=1.00, edge_recall=1.00, hallucination=0.00

---

## Eval 7: create_local_tables.py — flowchart TB — PASS

Single function, uses sqlite3 directly (no get_database() factory). sqlite3.connect() IS a terminal node (direct DB library call, not stdlib file I/O). No cross-file project calls.
GT nodes (5): create_local_tables, sqlite3.connect, cursor.execute, conn.commit, conn.close
GT edges (4): direct calls from create_local_tables to each terminal.
node_recall=1.00, edge_recall=1.00, hallucination=0.00

Key: sqlite3.connect() is included (direct DB library call) while yaml.load/json.load would be excluded (stdlib file I/O). Stdlib exclusion rule correctly distinguishes.

---

## Eval 8: pg_database_utility.py — classDiagram — PASS (0 edges)

Single class PostgresDatabaseUtility. Field `pool: ThreadedConnectionPool` (psycopg2, third-party — excluded by multi-file scan rule). Field `config: Dict` (stdlib generic — no edge). No project-class field types. 0 structural edges.
GT nodes (1): PostgresDatabaseUtility
GT edges (0): (vacuously 1.00 recall)
node_recall=1.00, edge_recall=1.00 (vacuous), hallucination=0.00

Consistent with local_recommender pattern from iteration 8.
