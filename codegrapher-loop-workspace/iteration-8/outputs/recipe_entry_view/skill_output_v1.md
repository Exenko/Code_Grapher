# Skill Output v1 — recipe_entry_view.py — classDiagram

## Metadata
- Skill node count: 2
- Skill edge count: 0

## Mermaid Diagram

```mermaid
classDiagram
    class IngredientRowWidget {
        +UNITS: list
        +remove_requested: Signal
        +__init__(parent=None)
        +_setup_ui()
        +get_data() Optional[Dict[str, str]]
        +clear()
    }

    class RecipeEntryView {
        +recipe_saved: Signal
        +recipe_submitted: Signal
        +navigate_to_view: Signal
        -_app_controller
        -_db_manager
        -_ingredient_rows: List[IngredientRowWidget]
        +__init__(parent=None, app_controller=None)
        +_setup_ui()
        +refresh_data()
        +clear_data()
        +on_view_activated()
    }
```

Skill nodes: 2, Skill edges: 0

## Notes
- Skill only read recipe_entry_view.py — found only IngredientRowWidget and RecipeEntryView
- Missing GT classes: AutocompleteEntryEnhanced, EnhancedAutocompletePopup, NumericEntry, YamlPreviewDialog, RecipeYamlConverter (all imported from other project files)
- Missing GT edge: AutocompleteEntryEnhanced → EnhancedAutocompletePopup (via _popup field, defined in imported file)
- Root cause: classDiagram skill prompt does not instruct reading imported local project class files
