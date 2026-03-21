# Ground Truth — allergen_indexer.py — classDiagram

## Metadata
- GT node count: 2
- GT edge count: 0

## Mermaid Diagram

```mermaid
classDiagram
    class AllergenHierarchy {
        +main_category: str
        +subcategory: str
        +specific_type: str
        +patterns: List[str]
    }

    class AllergenIndexer {
        +db
        +logger
        +allergen_dict: Dict
        +pattern_map
        +hierarchy_map
        +__init__(db_path: str, allergen_dict_path: Optional[str])
        +setup_logging()
        +process_ingredient_batch(batch: List[Tuple]) List[Tuple[int, str]]
        +index_allergens(batch_size: int, num_workers: int)
        +generate_allergen_report() Dict
        +populate_allergen_hierarchy(allergen_dict: dict)
        +generate_hierarchy_report() dict
    }
```

## Class Definitions
- **AllergenHierarchy**: dataclass with 4 fields (all built-in types: str, str, str, List[str])
- **AllergenIndexer**: class with db, logger, allergen_dict: Dict, pattern_map, hierarchy_map; 7 public methods

## Edge Definitions
**None** — `AllergenIndexer.pattern_map` contains AllergenHierarchy objects at runtime, but the declared field type is `Dict` (built-in). Edge rule: draw edges ONLY when declared type = local class. Dict ≠ AllergenHierarchy → no edge.

## Note for grading
This is a 0-edge diagram. Grading focus: does the skill correctly identify BOTH classes, and does it correctly draw NO edges (i.e., not incorrectly infer an edge from runtime usage or method signatures)?
