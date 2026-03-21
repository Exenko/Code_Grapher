# Skill Output — Server_Side/main.py

**Diagram type:** flowchart LR — shows sequential database initialization pipeline with circuit-breaker guards (success checks) between each major stage

**Graph files read:** sub/main_Server_Side_main.json

```mermaid
flowchart LR
    Start([Start]) --> Setup[Setup<br/>Logging]
    Setup --> Directories[Setup<br/>Directories]
    Directories --> Validate{Validate<br/>Data Files?}

    Validate -->|Success| CB1{Step 1<br/>Created?}
    CB1 -->|Yes| Step1[Step 1:<br/>Create DB<br/>Tables]
    Step1 --> CB2{Step 2<br/>Ready?}

    CB2 -->|Yes| Step2[Step 2:<br/>Import<br/>Data]
    Step2 --> CB3{Step 2b<br/>Ready?}

    CB3 -->|Yes| Step2b[Step 2b:<br/>Load Climate<br/>Ingredients]
    Step2b --> CB4{Step 3<br/>Ready?}

    CB4 -->|Yes| Step3[Step 3:<br/>Index<br/>Allergens]
    Step3 --> CB5{Step 4<br/>Ready?}

    CB5 -->|Yes| Step4[Step 4:<br/>Index Ingredient<br/>Overlap]
    Step4 --> CB6{Step 6<br/>Ready?}

    CB6 -->|Yes| Step6[Step 6:<br/>Load Lookup<br/>Tables]
    Step6 --> CB7{Step 7<br/>Ready?}

    CB7 -->|Yes| Step7[Step 7:<br/>Load Cuisine<br/>Hierarchy]
    Step7 --> CB8{Step 8<br/>Ready?}

    CB8 -->|Yes| Step8[Step 8:<br/>Load<br/>Taxonomy]
    Step8 --> CB9{Step 9<br/>Ready?}

    CB9 -->|Yes| Step9[Step 9:<br/>Import<br/>Recipes]
    Step9 --> CB10{Step 10<br/>Ready?}

    CB10 -->|Yes| Step10[Step 10:<br/>Derive Dietary<br/>Restrictions]
    Step10 --> Report[Generate<br/>Completion<br/>Report]
    Report --> End([Complete])

    Validate -->|Fail| Fail([Error])
    CB1 -->|No| Fail
    CB2 -->|No| Fail
    CB3 -->|No| Fail
    CB4 -->|No| Fail
    CB5 -->|No| Fail
    CB6 -->|No| Fail
    CB7 -->|No| Fail
    CB8 -->|No| Fail
    CB9 -->|No| Fail
    CB10 -->|No| Fail
```

**Nodes:** setup_logging, setup_directories, validate_data_files, step1_create_database_tables, step2_import_data, step2b_load_climate_ingredients, step3_index_allergens, step4_index_ingredient_overlap, step6_load_lookup_tables, step7_load_cuisine_hierarchy, step8_load_taxonomy, step9_import_recipes, step10_derive_dietary_restrictions, generate_completion_report

**Edges:**
- main --calls--> setup_logging (seq:1)
- main --calls--> setup_directories (seq:5)
- main --calls--> step1_create_database_tables (seq:7)
- main --calls--> step2_import_data (seq:13)
- main --calls--> step2b_load_climate_ingredients (seq:14)
- main --calls--> step3_index_allergens (seq:15)
- main --calls--> step4_index_ingredient_overlap (seq:16)
- main --calls--> step6_load_lookup_tables (seq:17)
- main --calls--> step7_load_cuisine_hierarchy (seq:18)
- main --calls--> step8_load_taxonomy (seq:19)
- main --calls--> step9_import_recipes (seq:20)
- main --calls--> step10_derive_dietary_restrictions (seq:21)
- main --calls--> generate_completion_report (seq:8)
- step2_import_data --calls--> validate_data_files (seq:10)
