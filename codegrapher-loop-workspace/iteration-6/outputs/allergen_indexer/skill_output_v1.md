# Skill Output v1 — allergen_indexer.py — classDiagram

## Analysis

**Classes found:** AllergenHierarchy, AllergenIndexer

**Field types analyzed:**
- `AllergenHierarchy`: 4 fields, all built-in types (str, str, str, List[str])
- `AllergenIndexer`: 5 fields:
  - `db`: untyped (external object)
  - `logger`: logging.Logger (external)
  - `allergen_dict: Dict` — built-in
  - `pattern_map: Dict[str, AllergenHierarchy]` — value type is AllergenHierarchy (local class) → EDGE DRAWN
  - `hierarchy_map: Dict[str, Set[str]]` — built-in

**Edges identified:**
- `AllergenIndexer --> AllergenHierarchy` via field `pattern_map: Dict[str, AllergenHierarchy]`
- Reasoning: AllergenHierarchy appears as value type in the generic container annotation

## Diagram

```mermaid
classDiagram
    class AllergenHierarchy {
        +main_category: str
        +subcategory: str
        +specific_type: str
        +patterns: List~str~
    }

    class AllergenIndexer {
        +db: object
        +logger: logging.Logger
        +allergen_dict: Dict
        +pattern_map: Dict~str,AllergenHierarchy~
        +hierarchy_map: Dict~str,Set~str~~
        +__init__(db_path: str, allergen_dict_path: Optional~str~)
        +setup_logging()
        +_load_allergen_dict(path: str) Dict
        +_ensure_database_structure() None
        +_validate_allergen_dict(allergen_dict: Dict) None
        +_build_pattern_maps() Tuple~Dict,Dict~
        +_parse_ingredients(text: str) List~str~
        +_find_allergens(text: str) Set~str~
        +process_ingredient_batch(batch: List~Tuple~) List~Tuple~
        +index_allergens(batch_size: int, num_workers: int)
        +generate_allergen_report() Dict
        +populate_allergen_hierarchy(allergen_dict: dict) None
        +generate_hierarchy_report() dict
    }

    AllergenIndexer --> AllergenHierarchy : pattern_map
```

## Notes
- Edge drawn because AllergenHierarchy appears as value type in `Dict[str, AllergenHierarchy]`
- GT drew 0 edges (strict rule: declared field type = Dict, not AllergenHierarchy)
- This exposes a RULE GAP: does `Dict[K, LocalClass]` count as a direct field type reference?
- The GT agent applied strict interpretation; skill applied loose interpretation
