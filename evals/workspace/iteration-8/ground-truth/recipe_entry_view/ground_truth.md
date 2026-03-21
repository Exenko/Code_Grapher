# Ground Truth — recipe_entry_view.py — classDiagram

## Metadata
- GT node count: 7
- GT edge count: 1

## Mermaid Diagram

```mermaid
classDiagram
    class IngredientRowWidget {
        +UNITS: list
        +remove_requested: Signal
        +name_entry: QLineEdit
        +qty_entry: QLineEdit
        +unit_combo: QComboBox
        +get_data() Optional[Dict]
        +clear()
    }

    class RecipeEntryView {
        +recipe_saved: Signal
        +recipe_submitted: Signal
        +navigate_to_view: Signal
        -_app_controller
        -_db_manager
        -_ingredient_rows: List[IngredientRowWidget]
        +refresh_data()
        +clear_data()
        +on_view_activated()
    }

    class AutocompleteEntryEnhanced {
        -_popup: Optional[EnhancedAutocompletePopup]
        -_autocomplete_type: str
        +get_sanitized() str
        +set_autocomplete_type(str)
    }

    class EnhancedAutocompletePopup {
        -_list_widget: QListWidget
        +set_items(List[str])
        +get_selected() Optional[str]
    }

    class NumericEntry {
        +allow_decimal: bool
        +get_value() Optional
        +is_valid() bool
    }

    class YamlPreviewDialog {
        -_yaml_content: str
        -_server_client: Optional
        +get_yaml_content() str
    }

    class RecipeYamlConverter {
        +form_to_yaml(Dict) str
        +yaml_to_form_data(str) Dict
    }

    AutocompleteEntryEnhanced --> EnhancedAutocompletePopup : _popup
```

## Actor Definitions
- **IngredientRowWidget** — row widget in recipe_entry_view.py
- **RecipeEntryView** — main view class in recipe_entry_view.py
- **AutocompleteEntryEnhanced** — imported from ui_new/components/autocomplete_entry.py
- **EnhancedAutocompletePopup** — imported from same file as AutocompleteEntryEnhanced
- **NumericEntry** — imported from ui_new/components/numeric_entry.py
- **YamlPreviewDialog** — imported from ui_new/dialogs/yaml_preview_dialog.py
- **RecipeYamlConverter** — imported from utils/recipe_yaml_converter.py

## Notes
- 1 structural edge: AutocompleteEntryEnhanced → EnhancedAutocompletePopup via `_popup: Optional[EnhancedAutocompletePopup]`
- RecipeEntryView._ingredient_rows: List[IngredientRowWidget] → NO edge (container type rule)
- Classes from imported project files ARE included in classDiagram (this is a multi-file diagram)
- GT agent read imported files to find classes used as field types across the file boundary
