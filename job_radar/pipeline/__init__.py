"""Pipeline stages.

Call order in `cli.run`:
  collect → normalize → hard_filter → (embed_recall M2) → (llm_scorer M2) → heuristic_scorer → tier
"""
