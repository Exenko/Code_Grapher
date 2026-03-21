# meal_plan_manager — Skill Agent v1 Output

**Version:** v1
**Graph sources used:** TYPE nodes, produces edges, calls edges
**Approach:** Each TYPE node becomes a class box. Enums use <<enumeration>> stereotype. Relationships derived from produces edges (dependency arrows from MealPlanManager to return types), composition from DinnerWithSides call chain, and enum-to-MealAssignment association from file proximity inference.

## Diagram

```mermaid
classDiagram
    class MealType {
        <<enumeration>>
    }

    class DayOfWeek {
        <<enumeration>>
    }

    class MealAssignment {
    }

    class DinnerWithSides {
    }

    class ScaledIngredient {
    }

    class AggregatedIngredient {
    }

    class MealPlanManager {
        +get_meal_assignment() MealAssignment
        +get_dinner_sides() MealAssignment
        +get_dinner_with_sides() DinnerWithSides
        +get_weekly_plan_detailed() MealAssignment
        +scale_recipe_ingredients() ScaledIngredient
    }

    MealAssignment --> MealType : uses
    MealAssignment --> DayOfWeek : uses
    DinnerWithSides *-- MealAssignment : dinner + sides
    MealPlanManager ..> MealAssignment : produces
    MealPlanManager ..> DinnerWithSides : produces
    MealPlanManager ..> ScaledIngredient : produces
    MealPlanManager ..> AggregatedIngredient : aggregates
```

## Counts
- **Class count:** 7
- **Relationship count:** 8

Confirm written.
