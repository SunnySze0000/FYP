# Model illustration provenance

`model_illustrations.py` creates synthetic teaching examples for Section 2.2. It does not load market data or report research performance.

- Random seed: 42, using NumPy's default random generator.
- Regression: 24 invented positive variance observations, fitted by ordinary least squares with an intercept.
- Clustering: 48 invented wallet feature points, standardised and grouped by a three-centroid k-means iteration. Marker shapes distinguish groups in monochrome. Crosses mark fitted centroids.
- Scenario loss: a hypothetical 60/40 mixture of two normal loss distributions, in percentage points. The illustration calculates its 95th percentile and conditional tail mean. This distribution is illustrative and does not prescribe normal returns for the actual scenario engine.

Run with Python and NumPy. The script writes `../model-coordinates.tex`. The proposal uses these coordinates through `../model-illustrations.tex` and PGFPlots. Commit the generator, coordinates and compiled proposal together after changes.

## Documentation supporting the proposed implementation

Checked on 9 September 2026. Settings in the proposal are starting choices, not measured outcomes or commitments to use every candidate.

- [CrewAI Flows](https://docs.crewai.com/en/concepts/flows), [custom tools](https://docs.crewai.com/en/concepts/tools), and [MCP adapter](https://docs.crewai.com/en/mcp/overview).
- [Sentence Transformers all-MiniLM-L6-v2 model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2): 384-dimensional embeddings and a default 256-word-piece input limit. Chunk sizes in the draft are measured with this model's tokenizer.
- [pgvector](https://github.com/pgvector/pgvector) and [Python/SQLAlchemy integration](https://github.com/pgvector/pgvector-python).
- [scikit-learn supervised estimators](https://scikit-learn.org/stable/supervised_learning.html), [probability calibration](https://scikit-learn.org/stable/modules/calibration.html), and [KMeans](https://scikit-learn.org/stable/modules/generated/sklearn.cluster.KMeans.html).
- [TanStack Query](https://tanstack.com/query/latest/docs/framework/react/overview), [FastAPI request bodies](https://fastapi.tiangolo.com/tutorial/body/), [SQLAlchemy](https://docs.sqlalchemy.org/en/20/orm/quickstart.html), and [Alembic](https://alembic.sqlalchemy.org/en/latest/).
- [HTTPX](https://www.python-httpx.org/) and [Polars Parquet output](https://docs.pola.rs/api/python/stable/reference/api/polars.DataFrame.write_parquet.html).
