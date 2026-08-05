# genai-block8-capstone
Flagship end-to-end agentic app — integrates a graph knowledge base, RAG retrieval, and a hardened multi-agent system into one deployed, observable pipeline.

## Operational notes

- **Rotating `NEO4J_PASSWORD`:** Neo4j only reads `NEO4J_AUTH` (which `docker-compose.yml` builds from `.env`'s `NEO4J_USER`/`NEO4J_PASSWORD`) when it initializes an empty database. The `neo4j_data` volume persists across `docker compose up`/`down`, so changing `NEO4J_PASSWORD` in `.env` after the first run has no effect — Neo4j keeps the old credentials, the healthcheck fails, and `graph-seed`/`app` never start. Run `docker compose down -v` first (this drops `neo4j_data`, so the graph reseeds from `graph-seed` on the next `up`), then change the password and start again.
