# seasonal_indexer — Skill Agent v1 Output

**Version:** v1
**Graph sources used:** calls edges with seq, cross_file edges to db_factory
**Approach:** Ordered pipeline steps by seq number on process_all_seasonal_data calls; mapped cross-file edges to db_factory.get_placeholder as DB interaction nodes; surfaced recursive call in process_seasonal_hierarchy as a self-loop; grouped sub-calls within each pipeline stage.

## Diagram

```mermaid
flowchart TB
    main["main()"]
    init["SeasonalIndexer.__init__\n(instantiate)"]
    setup_log["setup_logging()"]
    db_connect[("DB\nconnect")]

    isb["initialize_seasonal_buckets()\nseq=2"]
    itm["initialize_term_mappings()\nseq=3"]
    lsi["load_seasonal_inheritance()\nseq=4"]
    cism["create_ingredient_seasonality_mappings()\nseq=5"]
    psh["process_seasonal_hierarchy()\nseq=7"]

    fsf["find_seasonality_for_hierarchy()\n(per ingredient, seq=8)"]
    gahi["get_allergen_hierarchy_ids()\nseq=1"]
    csr["create_seasonality_record()\nseq=3"]

    json_file[/"JSON file\n(seasonal inheritance data)"/]
    DB[("Database\ndb_factory.get_placeholder")]

    main --> init
    init --> setup_log
    init --> db_connect

    init --> isb
    isb --> itm
    itm --> lsi
    lsi --> cism
    cism --> psh

    lsi -- "reads" --> json_file

    isb -- "DB write\nSeasonalBuckets" --> DB
    itm -- "DB write\nSeasonalTermMapping" --> DB

    cism --> fsf
    fsf -- "DB read\nhierarchy fallback\ntype->subcategory->category" --> DB
    cism -- "DB read\nIngredientAllergens\nAllergenSeasonality" --> DB
    cism -- "DB write\nIngredientSeasonality" --> DB

    psh --> gahi
    gahi -- "DB read\nAllergenCategories\nSubcategories / Types" --> DB
    psh -- "recursive DFS\n(sub-nodes)" --> psh
    psh --> csr
    csr -- "DB write\nAllergenSeasonality" --> DB
```

## Counts
- **Node count:** 15
- **Edge count:** 20

Confirm written.
