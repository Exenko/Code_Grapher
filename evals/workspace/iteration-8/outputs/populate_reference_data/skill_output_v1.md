# Skill Output v1 — populate_reference_data.py — flowchart TB

## Metadata
- Skill node count: 16
- Skill edge count: 35 (diagram count)

## Mermaid Diagram

```mermaid
flowchart TB
    A["populate_all_reference_data()"]
    B["populate_geographic_hierarchy_from_json()"]
    C["populate_allergen_hierarchy_from_json()"]
    D["populate_diet_types_from_json()"]
    E["populate_equipment_types_from_json()"]
    F["populate_storage_types_from_json()"]
    G["populate_climate_seasonality()"]
    H["insert_hierarchy_records()"]
    I["insert_allergen_records()"]
    J["_insert_climate_bucket_ranges()"]

    K["sqlite3.connect()"]
    L["cursor.execute()"]
    M["cursor.executemany()"]
    N["conn.commit()"]
    O["conn.close()"]
    P["conn.rollback()"]

    A --> B
    A --> C
    A --> D
    A --> E
    A --> F
    A --> G

    B --> H
    C --> I
    G --> J

    D --> K
    D --> L
    D --> N
    D --> O

    E --> K
    E --> L
    E --> N
    E --> O

    F --> K
    F --> L
    F --> N
    F --> O

    H --> K
    H --> M
    H --> N
    H --> O

    I --> K
    I --> M
    I --> N
    I --> O

    G --> K
    G --> L
    G --> N
    G --> P
    G --> O

    J --> L
```

Skill nodes: 16, Skill edges: 35

## Notes
- Skill correctly applied shared terminal node pattern (one sqlite3.connect() for all callers)
- json.load correctly excluded (file I/O is not a cross-file terminal node)
- GT had 45 nodes with per-call-site duplication (sqlite3.connect × 6, cursor.execute × 5, etc.)
- Skill's 16 nodes cover 40/45 GT node concepts via shared nodes
- json.load nodes in GT (5 instances) are not covered by skill — but may be a GT calibration error
