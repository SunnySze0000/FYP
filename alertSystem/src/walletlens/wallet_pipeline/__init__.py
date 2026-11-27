"""The team's wallet pipeline from the FYP repo (feature/cluster-implied-probabilities), reused as is:

1. ``owners``     sniper / same-owner grouping from repeated co-timed trading (union-find into entities)
2. ``rules``      transparent hard rules that filter out bots, dust and one-off wallets
3. ``behaviour``  behaviour features per entity and KMeans clustering, frozen once fitted

``adapter`` converts WalletLens's canonical trades into the column names these modules expect.
"""
