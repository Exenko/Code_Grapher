# ingredients_routes — Ground Truth sequenceDiagram

**Source files:** Server_Side/api/routes/ingredients.py, Server_Side/db/db_factory.py, Server_Side/db/config.py
**Diagram type:** sequenceDiagram

## Diagram

```mermaid
sequenceDiagram
    participant Client
    participant IngredientsRouter
    participant db_factory
    participant Database
    participant DataVersions

    Note over Client,DataVersions: Route 1 — GET /api/ingredients/master

    Client ->> IngredientsRouter: GET /api/ingredients/master
    IngredientsRouter ->> db_factory: get_database()
    Note over db_factory: DB_TYPE is always 'postgresql' — SQLite branch is dead code
    db_factory -->> IngredientsRouter: PostgresDatabaseUtility instance
    IngredientsRouter ->> Database: SELECT id, name, canonical_name, category, subcategory, taxonomy_path, aliases FROM MasterIngredients ORDER BY id
    Database -->> IngredientsRouter: rows
    IngredientsRouter ->> IngredientsRouter: fetchall(); parse aliases JSON per row
    IngredientsRouter ->> DataVersions: SELECT content_hash FROM DataVersions WHERE data_type = 'master_ingredients'
    DataVersions -->> IngredientsRouter: hash_result (or None -> "unknown")
    IngredientsRouter -->> Client: 200 {data: [...], hash: content_hash, count: N}

    Note over Client,DataVersions: Route 2 — GET /api/ingredients/seasonality/{climate_zone}

    Client ->> IngredientsRouter: GET /api/ingredients/seasonality/{climate_zone}
    IngredientsRouter ->> IngredientsRouter: validate climate_zone in CLIMATE_ZONES list
    alt Invalid climate_zone
        IngredientsRouter -->> Client: 400 {detail: "Invalid climate_zone '...'"}
    else Valid climate_zone
        IngredientsRouter ->> db_factory: get_database()
        db_factory -->> IngredientsRouter: PostgresDatabaseUtility instance
        IngredientsRouter ->> Database: SELECT ingredient_id, tier, varieties, peak_buckets, available_buckets, limited_buckets, confidence, notes, native_zones FROM IngredientSeasonality WHERE climate_zone = %s ORDER BY ingredient_id
        Database -->> IngredientsRouter: rows
        IngredientsRouter ->> IngredientsRouter: fetchall(); parse 5 JSONB fields per row
        IngredientsRouter ->> DataVersions: SELECT content_hash FROM DataVersions WHERE data_type = 'seasonality_{climate_zone}'
        DataVersions -->> IngredientsRouter: hash_result (or None -> "unknown")
        IngredientsRouter -->> Client: 200 {climate_zone: zone, data: [...], hash: content_hash, count: N}
    end
```

## Ground Truth Counts
- **Actor count:** 5 (Client, IngredientsRouter, db_factory, Database, DataVersions)
- **Message count:** 20 total arrows across both routes (Route 1: 9, Route 2: 11 including the 400 branch)
- **Notes:** DB_TYPE is hardcoded to 'postgresql' in config.py — SQLite branches in both handlers are dead code. get_placeholder() executes once at module load time (not per-request). DataVersions modeled as separate participant because each route issues two distinct queries. get_database() creates a new PostgresDatabaseUtility instance on every request. Both routes catch bare Exception and re-raise as HTTPException(500).
