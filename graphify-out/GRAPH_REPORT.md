# Graph Report - src  (2026-08-19)

## Corpus Check
- Corpus is ~17,156 words - fits in a single context window. You may not need a graph.

## Summary
- 389 nodes · 824 edges · 13 communities (11 shown, 2 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 23 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Active Learning Utilities
- Loop Generalization
- GDB Connection Management
- Grammar Compaction
- Grammar Mining (PTA)
- Fuzzer Evaluation
- Control Flow Graph Utilities
- Grammar Processing Pipeline
- Tree Miner
- Fuzzing Engine
- Token Generalization
- Token Generalization Config
- STM32 GDB Instance

## God Nodes (most connected - your core abstractions)
1. `SUTInstance` - 52 edges
2. `GDBTracer` - 27 edges
3. `TokenGeneralizer` - 18 edges
4. `ConnectionBaseClass` - 16 edges
5. `STM32Instance` - 16 edges
6. `SUTConnection` - 15 edges
7. `main()` - 14 edges
8. `TreeBuilder` - 14 edges
9. `MSP430Instance` - 13 edges
10. `LimitFuzzer` - 12 edges

## Surprising Connections (you probably didn't know these)
- `LoopGeneralizer` --uses--> `GDBTracer`  [INFERRED]
  miner/loop_generalizer.py → tracer/gdb_tracer.py
- `MethodGeneralizer` --uses--> `GDBTracer`  [INFERRED]
  miner/method_generalizer.py → tracer/gdb_tracer.py
- `TokenGeneralizer` --uses--> `GDBTracer`  [INFERRED]
  miner/token_generalizer.py → tracer/gdb_tracer.py
- `TokenGeneralizer` --uses--> `SUTInstance`  [INFERRED]
  miner/token_generalizer.py → tracer/instance/sut_instance.py
- `collapse_alts()` --calls--> `generate_grammar()`  [EXTRACTED]
  miner/mine.py → cmimid/pta.py

## Import Cycles
- None detected.

## Communities (13 total, 2 thin omitted)

### Community 0 - "Active Learning Utilities"
Cohesion: 0.07
Nodes (15): get_compatibility_pattern(), identify_compatibility_patterns(), is_a_replaceable_with_b(), is_compatible(), Checks if the given node can be interchanged with the given list of nodes and…, register_node(), LoopGeneralizer, ConfigParser (+7 more)

### Community 1 - "Loop Generalization"
Cohesion: 0.08
Nodes (42): can_the_loop_be_deleted(), collect_pseudo_nodes(), generalize_loop_trees(), main(), update_original_pseudo_names(), update_pseudo_name(), usage(), collect_nodes() (+34 more)

### Community 2 - "GDB Connection Management"
Cohesion: 0.08
Nodes (12): Queue, ConnectionBaseClass, ConfigParser, Sends 'input' to SUT Returns True if input was accepted, Blocks until SUT can receive input, [Optional], free connection resources Example: Close TCP socket., SerialConnection, ConfigParser (+4 more)

### Community 3 - "Grammar Compaction"
Cohesion: 0.12
Nodes (33): main(), usage(), cleanup_token_names(), collect_duplicate_rule_keys(), collect_replacement_keys(), compact_grammar(), find_focused_rules(), find_reachable_keys() (+25 more)

### Community 4 - "Grammar Mining (PTA)"
Cohesion: 0.09
Nodes (21): check_empty_rules(), check_grammar(), check_key(), collapse_alts(), collapse_rules(), convert_spaces_in_keys(), convert_to_grammar(), main() (+13 more)

### Community 5 - "Fuzzer Evaluation"
Cohesion: 0.11
Nodes (23): find_output_directory(), main(), Path, setup_logging(), find_output_directory(), main(), Path, Create a copy of `grammar` where all unused and unreachable nonterminals are… (+15 more)

### Community 6 - "Control Flow Graph Utilities"
Cohesion: 0.17
Nodes (15): DiGraph, all_back_edges(), all_natural_loops(), build_control_flow_graphs_from_traces(), if_else_scope(), natural_loop(), post_dominator_graph(), pre_dominator_graph() (+7 more)

### Community 7 - "Grammar Processing Pipeline"
Cohesion: 0.17
Nodes (16): asciimap_to_nt(), enhance_grammar(), main(), usage(), check_empty_rules(), collapse_alts(), collapse_rules(), convert_spaces_in_keys() (+8 more)

### Community 8 - "Tree Miner"
Cohesion: 0.19
Nodes (19): attach_comparisons(), does_item_overlap(), has_overlap(), indexes_to_children(), is_included(), is_second_item_included(), last_comparisons(), main() (+11 more)

### Community 9 - "Fuzzing Engine"
Cohesion: 0.16
Nodes (4): Fuzzer, LimitFuzzer, main(), usage()

### Community 10 - "Token Generalization"
Cohesion: 0.24
Nodes (14): do_n(), fill_tree(), find_max_generalized(), find_max_widened(), generalize_single_token(), generalize_tokens(), get_list_of_single_chars(), is_nt() (+6 more)

## Knowledge Gaps
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `SUTInstance` connect `Active Learning Utilities` to `GDB Connection Management`, `Token Generalization Config`, `STM32 GDB Instance`, `Fuzzer Evaluation`?**
  _High betweenness centrality (0.236) - this node is a cross-community bridge._
- **Why does `GDBTracer` connect `Fuzzer Evaluation` to `Active Learning Utilities`, `GDB Connection Management`, `Token Generalization Config`, `STM32 GDB Instance`?**
  _High betweenness centrality (0.117) - this node is a cross-community bridge._
- **Why does `SUTConnection` connect `GDB Connection Management` to `Active Learning Utilities`, `STM32 GDB Instance`?**
  _High betweenness centrality (0.100) - this node is a cross-community bridge._
- **Are the 8 inferred relationships involving `SUTInstance` (e.g. with `get_compatibility_pattern()` and `identify_compatibility_patterns()`) actually correct?**
  _`SUTInstance` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `GDBTracer` (e.g. with `main()` and `main()`) actually correct?**
  _`GDBTracer` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `TokenGeneralizer` (e.g. with `GDBTracer` and `SUTInstance`) actually correct?**
  _`TokenGeneralizer` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `STM32Instance` (e.g. with `GDBTracer` and `SUTConnection`) actually correct?**
  _`STM32Instance` has 2 INFERRED edges - model-reasoned connections that need verification._