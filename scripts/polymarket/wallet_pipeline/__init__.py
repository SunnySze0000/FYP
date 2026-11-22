"""Three-stage wallet pipeline: same-owner grouping -> hard rules -> behaviour clusters.

Each stage takes and returns plain DataFrames, so any stage can be replaced
(for example, an on-chain funding-graph owner detector) without touching the
others. The final membership table feeds ``cluster_implied_probability``.
"""
