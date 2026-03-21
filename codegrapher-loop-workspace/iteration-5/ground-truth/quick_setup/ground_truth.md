# Ground Truth: quick_setup.py — sequenceDiagram

## Metadata
- GT actor count: 5 (quick_setup, create_local_tables, populate_reference_data, export_overlap_hierarchy, overlap_sync_manager)
- GT message count: 9 cross-file calls (excludes intra-actor self-calls)
- Source: Client_Side/first_boot/quick_setup.py

## Mermaid diagram
```mermaid
sequenceDiagram
  participant QuickSetup as quick_setup
  participant CreateTables as create_local_tables
  participant PopulateRef as populate_reference_data
  participant ExportServer as export_overlap_hierarchy
  participant OverlapSync as overlap_sync_manager

  QuickSetup ->> CreateTables: create_local_tables("household.db")
  CreateTables -->> QuickSetup: schema created

  QuickSetup ->> PopulateRef: ReferenceDataPopulator("household.db")
  PopulateRef ->> PopulateRef: populate_all_reference_data()
  PopulateRef ->> PopulateRef: populate_geographic_hierarchy_from_json()
  PopulateRef ->> PopulateRef: populate_allergen_hierarchy_from_json()
  PopulateRef ->> PopulateRef: populate_diet_types_from_json()
  PopulateRef ->> PopulateRef: populate_equipment_types_from_json()
  PopulateRef ->> PopulateRef: populate_storage_types_from_json()
  PopulateRef ->> PopulateRef: populate_climate_seasonality()
  PopulateRef -->> QuickSetup: reference data populated

  alt Server database exists
    QuickSetup ->> ExportServer: export_overlap_hierarchy(server_db_path)
    ExportServer -->> QuickSetup: {categories, version_hash, metadata}

    QuickSetup ->> OverlapSync: OverlapSyncManager("household.db")
    QuickSetup ->> OverlapSync: sync_hierarchy_from_server(categories, version_hash)
    OverlapSync ->> OverlapSync: clear & repopulate OverlapHierarchy
    OverlapSync -->> QuickSetup: sync count
  else Server database missing
    QuickSetup -->> QuickSetup: skip (deferred sync)
  end
```

## Notes
Cross-file actors (5): quick_setup, create_local_tables, populate_reference_data, export_overlap_hierarchy (Server_Side), overlap_sync_manager.

Cross-file calls from quick_setup:
1. create_local_tables("household.db")
2. ReferenceDataPopulator("household.db") — constructor
3. export_overlap_hierarchy(server_db_path)
4. OverlapSyncManager("household.db") — constructor
5. sync_hierarchy_from_server(categories, version_hash)

The export_overlap_hierarchy is a conditional import (alt block) — only runs if server DB exists.
populate_reference_data self-calls are internal methods within that file — may not be visible in graph.
