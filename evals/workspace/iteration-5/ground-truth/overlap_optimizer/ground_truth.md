# Ground Truth: overlap_optimizer.py — classDiagram

## Metadata
- GT node count: 3
- GT edge count: 1
- Source: Client_Side/utils/overlap_optimizer.py

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
    +__init__(db_path)
    +get_recipe_categories(recipe_id, server_conn)
    +load_recipes_with_overlap(recipe_ids, server_db_path)
    +calculate_overlap_score(recipe, selected_categories, target_selection_size)
    +optimize_weekly_selection(candidate_recipes, num_recipes)
    +_calculate_selection_metrics(selected, selected_categories)
    +get_category_names(category_ids)
  }

  WeeklySelectionResult --> RecipeOverlap : selected_recipes
```

## Notes
Single edge: WeeklySelectionResult.selected_recipes is declared as List[RecipeOverlap] — explicit field-type relationship.

Excluded:
- Method parameters (recipe: RecipeOverlap, candidate_recipes: List[RecipeOverlap]) — parameter types, not fields
- Return types (functions returning RecipeOverlap or WeeklySelectionResult) — not structural
- OverlapOptimizer has no field of type RecipeOverlap or WeeklySelectionResult
