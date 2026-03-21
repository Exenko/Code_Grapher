# Iteration 3 — Eval Workspace

5 entry points. Focus: classDiagram, harder sequenceDiagram, single-file stateDiagram-v2, flowchart pipeline.

## Eval Set

| # | Entry Point | Diagram Type | Key Test |
|---|---|---|---|
| 1 | Client_Side/utils/autofill_engine.py | classDiagram | 13 type nodes, produces/consumes → composition |
| 2 | Client_Side/utils/meal_plan_manager.py | classDiagram | 2 enums + 4 dataclasses + 1 manager, composition |
| 3 | Server_Side/db/seasonal_indexer.py | flowchart TB | 5-step ETL pipeline, single class |
| 4 | Server_Side/api/routes/ingredients.py | sequenceDiagram | 2 routes, multi-actor (client→router→db), harder than server_api |
| 5 | Client_Side/utils/recipe_queue_manager.py | stateDiagram-v2 | single-file 3-state machine (queue→served→rejected) |

## Structure

ground-truth/
  autofill_engine/ground_truth.md
  meal_plan_manager/ground_truth.md
  seasonal_indexer/ground_truth.md
  ingredients_routes/ground_truth.md
  recipe_queue_manager/ground_truth.md

outputs/
  autofill_engine/skill_output_v1.md
  meal_plan_manager/skill_output_v1.md
  seasonal_indexer/skill_output_v1.md
  ingredients_routes/skill_output_v1.md
  recipe_queue_manager/skill_output_v1.md

evals/
  grading_v3.json

## Thresholds
- node_recall >= 0.80
- edge_recall >= 0.70
- hallucination_rate <= 0.15
