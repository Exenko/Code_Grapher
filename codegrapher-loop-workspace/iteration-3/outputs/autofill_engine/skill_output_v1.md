# autofill_engine — Skill Agent v1 Output

**Version:** v1
**Graph sources used:** TYPE nodes, produces/consumes edges, sub-graph
**Approach:** Derived class relationships from produces/consumes edge pairs at each pipeline stage. When function F consumes type B to produce type A, drew A ..> B (A depends on B). Used composition for LeftoverBank→LeftoverEntry based on method-level produces edge.

## Diagram

```mermaid
classDiagram
    class MealRequirement {
        <<dataclass>>
    }
    class CookingOpportunity {
        <<dataclass>>
    }
    class CookingSession {
        <<dataclass>>
    }
    class UnassignedMeal {
        <<dataclass>>
    }
    class AssignedSession {
        <<dataclass>>
    }
    class IngredientTracker {
        <<dataclass>>
    }
    class RecipeScore {
        <<dataclass>>
    }
    class ScoredRecipe {
        <<dataclass>>
    }
    class RerollOptions {
        <<dataclass>>
    }
    class LeftoverEntry {
        <<dataclass>>
    }
    class LeftoverBank {
    }
    class ConsolidatedIngredient {
        <<dataclass>>
    }
    class ShoppingList {
        <<dataclass>>
    }

    LeftoverBank *-- LeftoverEntry
    CookingOpportunity ..> MealRequirement : identify_cooking_opportunities
    CookingSession ..> CookingOpportunity : calculate_cooking_sessions
    UnassignedMeal ..> CookingOpportunity : calculate_cooking_sessions
    RecipeScore ..> CookingSession : score_recipe_for_session
    RecipeScore ..> IngredientTracker : score_recipe_for_session
    AssignedSession ..> CookingSession : assign_recipes_to_sessions
    AssignedSession ..> IngredientTracker : assign_recipes_to_sessions
    IngredientTracker ..> CookingSession : assign_recipes_to_sessions
    RerollOptions ..> AssignedSession : reroll_session_recipe
    RerollOptions ..> IngredientTracker : reroll_session_recipe
    ShoppingList ..> AssignedSession : generate_shopping_list
```

## Counts
- **Class count:** 13
- **Relationship count:** 12 (1 composition, 11 dependency associations)

Confirm written.
