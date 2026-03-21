# meal_plan_manager — Ground Truth classDiagram

**Source file:** Client_Side/utils/meal_plan_manager.py
**Diagram type:** classDiagram

## Diagram

```mermaid
classDiagram
    class MealType {
        <<enumeration>>
        BREAKFAST
        LUNCH
        DINNER
        SIDE
        DESSERT
    }

    class DayOfWeek {
        <<enumeration>>
        MONDAY
        TUESDAY
        WEDNESDAY
        THURSDAY
        FRIDAY
        SATURDAY
        SUNDAY
    }

    class MealAssignment {
        +str plan_id
        +int household_id
        +date week_start_date
        +int day_of_week
        +str meal_type
        +Optional~int~ recipe_id
        +Optional~int~ assigned_by
        +Optional~str~ notes
        +Optional~str~ parent_meal_id
        +int side_order
        +Optional~datetime~ modified_date
    }

    class DinnerWithSides {
        +Optional~MealAssignment~ dinner
        +List~MealAssignment~ sides
        +dinner_recipe_id() Optional~int~
        +side_recipe_ids() List~int~
        +all_recipe_ids() List~int~
    }

    class ScaledIngredient {
        +int ingredient_id
        +Optional~str~ ingredient_name
        +float quantity
        +str unit
        +int recipe_id
        +float original_quantity
        +str original_unit
    }

    class AggregatedIngredient {
        +int ingredient_id
        +Optional~str~ ingredient_name
        +float total_quantity
        +str unit
        +int recipe_count
        +List~int~ recipes
    }

    class MealPlanManager {
        +str db_path
        +__init__(db_path) None
        +assign_recipe_to_meal(household_id, week_start_date, day_of_week, meal_type, recipe_id, assigned_by, notes) bool
        +assign_side_to_dinner(household_id, week_start_date, day_of_week, recipe_id, side_order, assigned_by, notes) Optional~str~
        +get_dinner_sides(household_id, week_start_date, day_of_week) List~MealAssignment~
        +get_dinner_with_sides(household_id, week_start_date, day_of_week) DinnerWithSides
        +get_weekly_plan(household_id, week_start_date) Dict
        +get_weekly_plan_detailed(household_id, week_start_date) Dict
        +remove_meal(household_id, week_start_date, day_of_week, meal_type) bool
        +update_meal(household_id, week_start_date, day_of_week, meal_type, new_recipe_id, notes) bool
        +update_side(household_id, week_start_date, day_of_week, side_order, new_recipe_id, notes) bool
        +scale_recipe_ingredients(recipe_ingredients, original_servings, target_servings) List~ScaledIngredient~
        +generate_shopping_list(household_id, week_start_date, recipes_with_ingredients) bool
        +get_shopping_list(household_id, week_start_date) List~Dict~
        +check_off_ingredient(household_id, week_start_date, ingredient_id, checked) bool
        +get_meal_assignment(household_id, week_start_date, day_of_week, meal_type) Optional~MealAssignment~
        +get_meals_by_recipe(household_id, recipe_id) List~Tuple~
        +get_week_start_date(target_date) date
        +clear_weekly_plan(household_id, week_start_date) bool
        +get_meals_stats(household_id, week_start_date) Dict
    }

    DinnerWithSides o-- MealAssignment : dinner / sides
    MealPlanManager --> MealAssignment : creates / returns
    MealPlanManager --> DinnerWithSides : returns
    MealPlanManager --> ScaledIngredient : returns
```

## Ground Truth Counts
- **Node count:** 7
- **Edge count:** 4
- **Notes:** DinnerWithSides has two fields typed MealAssignment (dinner and sides) — one aggregation edge since both point to the same class. AggregatedIngredient is defined but only instantiated locally inside generate_shopping_list — never returned from a public method, so no edge drawn to it. MealPlanManager does not inherit from any class in this file. DinnerWithSides has three @property methods shown as class methods. No enum associations drawn — MealPlanManager uses raw strings rather than enum instances in method signatures.
