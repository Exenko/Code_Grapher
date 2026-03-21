# Skill Output v1 — reference_data_loader.py — flowchart TB

## Metadata
- Skill node count: 15 (diagram count)
- Skill edge count: 13 (diagram count)

## Mermaid Diagram

```mermaid
graph TB
    get_ref["get_reference_data_loader()"]
    init["__init__()"]
    load_all["_load_all_data()"]
    load_json["_load_json()"]
    load_json_keys["_load_json_keys()"]
    extract_cuisine["_extract_all_cuisine_paths()"]
    extract_allergen["_extract_allergen_categories()"]
    get_sugg["get_suggestions()"]
    get_cuisine["get_cuisine_suggestions()"]
    get_simple["_get_simple_suggestions()"]
    sanitize["sanitize_input()"]
    sanitize_single["_sanitize_single()"]

    json_load["json.load()"]
    open_file["open()"]
    path_exists["Path.exists()"]

    get_ref --> init
    init --> load_all
    load_all --> load_json
    load_all --> extract_cuisine
    load_all --> load_json_keys
    load_all --> extract_allergen
    load_json_keys --> load_json
    load_json --> path_exists
    load_json --> open_file
    load_json --> json_load
    get_sugg --> get_cuisine
    get_sugg --> get_simple
    sanitize --> sanitize_single
```

Skill nodes: 15, Skill edges: 13

## Notes
- Extra nodes: json_load, open_file, path_exists (stdlib calls incorrectly treated as cross-file terminal nodes)
- Missing GT edge: get_cuisine_suggestions → _extract_all_cuisine_paths
- Missing GT nodes: ReferenceDataLoader() and __new__() (constructor detail; GT calibration issue)
- Root cause: cross-file terminal nodes rule applied to stdlib (json, pathlib) instead of only project-internal DB utilities
