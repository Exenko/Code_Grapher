# Skill Output: overlap_optimizer.py — classDiagram

## Graph data summary
- TYPE nodes (classes): RecipeOverlap, WeeklySelectionResult, OverlapOptimizer (3 total)
- SYMBOL nodes: 20 (methods and dataclass fields)
- Structural edges: 1 — WeeklySelectionResult.selected_recipes uses_type RecipeOverlap

## Mermaid diagram
```mermaid
classDiagram
  class RecipeOverlap {
    +recipe_id: int
    +recipe_title: str
    +primary_categories: Dict
    +all_categories: Set
    +category_count: int
    +base_score: float
    +overlap_score: float
  }

  class WeeklySelectionResult {
    +selected_recipes: List
    +overlap_percentage: float
    +shared_categories: Dict
    +variety_score: float
    +shopping_efficiency: float
  }

  class OverlapOptimizer {
    -TARGET_OVERLAP: float
    -TARGET_VARIETY: float
    -MAX_CATEGORY_REUSE: int
    -ROLE_WEIGHTS: Dict
    -db_path: str
    +get_recipe_categories()
    +load_recipes_with_overlap()
    +calculate_overlap_score()
    +optimize_weekly_selection()
    +_calculate_selection_metrics()
    +get_category_names()
  }

  WeeklySelectionResult --> RecipeOverlap : selected_recipes
```

## Reasoning
Edge drawn: WeeklySelectionResult.selected_recipes declared as List[RecipeOverlap] — confirmed by graph uses_type edge on field declaration.
Excluded: produces/consumes edges (function return types = pipeline flow, not structural), calls edges (control flow), OverlapOptimizer method-local usages of RecipeOverlap (not stored as fields).
