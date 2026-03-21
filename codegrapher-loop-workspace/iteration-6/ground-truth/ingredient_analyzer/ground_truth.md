# Ground Truth — ingredient_analyzer.py — classDiagram

## Metadata
- GT node count: 3
- GT edge count: 1

## Mermaid Diagram

```mermaid
classDiagram
    class IngredientUsage {
        +ingredient_id: int
        +ingredient_name: str
        +usage_count: int
        +recipe_ids: List[int]
        +role: Optional[str]
    }

    class WeeklyIngredientAnalysis {
        +efficiency_score: float
        +total_unique_ingredients: int
        +total_ingredient_uses: int
        +overlap_percentage: float
        +proteins: Dict[str, int]
        +vegetables: Dict[str, int]
        +carbs: Dict[str, int]
        +protein_types_count: int
        +vegetable_types_count: int
        +carb_types_count: int
        +top_overlapping_ingredients: List[IngredientUsage]
        +needs_more_proteins: bool
        +needs_more_vegetables: bool
        +needs_more_carbs: bool
    }

    class IngredientAnalyzer {
        +db_path: str
        +MIN_PROTEIN_TYPES: int
        +MAX_PROTEIN_TYPES: int
        +MIN_VEGETABLE_TYPES: int
        +MAX_VEGETABLE_TYPES: int
        +MIN_CARB_TYPES: int
        +MAX_CARB_TYPES: int
        +EXCELLENT_OVERLAP: float
        +GOOD_OVERLAP: float
        +FAIR_OVERLAP: float
        +__init__(db_path: str)
        +_get_connection()
        +analyze_weekly_plan(household_id: int, week_start_date: date) Optional[WeeklyIngredientAnalysis]
        +get_efficiency_stars(overlap_percentage: float) int
        +format_efficiency_stars(stars: int) str
    }

    WeeklyIngredientAnalysis --> IngredientUsage : top_overlapping_ingredients
```

## Class Definitions
- **IngredientUsage**: dataclass, 5 fields all built-in types
- **WeeklyIngredientAnalysis**: dataclass, 14 fields; field `top_overlapping_ingredients: List[IngredientUsage]` references local class
- **IngredientAnalyzer**: regular class, db_path + 9 class constants, 5 methods; no field references to local classes

## Edge Definitions
- **WeeklyIngredientAnalysis --> IngredientUsage** via field `top_overlapping_ingredients: List[IngredientUsage]`
- Note: IngredientAnalyzer.analyze_weekly_plan() returns WeeklyIngredientAnalysis — this is a return type, NOT a field, so NO edge drawn
