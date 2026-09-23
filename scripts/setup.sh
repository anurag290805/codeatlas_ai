#!/bin/bash
# CodeAtlas AI - Project Scaffolding Script
# Run this from the project root: bash scripts/setup.sh

set -e

echo "Creating CodeAtlas AI folder structure..."

# ---------- BACKEND ----------
mkdir -p backend/app/api
mkdir -p backend/app/core
mkdir -p backend/app/models
mkdir -p backend/app/db
mkdir -p backend/app/utils
mkdir -p backend/tests

touch backend/app/__init__.py
touch backend/app/main.py
touch backend/app/config.py

touch backend/app/api/__init__.py
touch backend/app/api/routes_repo.py
touch backend/app/api/routes_query.py
touch backend/app/api/routes_graph.py

touch backend/app/core/__init__.py
touch backend/app/core/git_handler.py
touch backend/app/core/parser.py
touch backend/app/core/embeddings.py
touch backend/app/core/vector_store.py
touch backend/app/core/retriever.py
touch backend/app/core/llm.py
touch backend/app/core/graph_builder.py

touch backend/app/models/__init__.py
touch backend/app/models/schemas.py
touch backend/app/models/db_models.py

touch backend/app/db/__init__.py
touch backend/app/db/database.py
touch backend/app/db/crud.py

touch backend/app/utils/__init__.py
touch backend/app/utils/logger.py
touch backend/app/utils/file_utils.py

touch backend/tests/__init__.py
touch backend/tests/test_parser.py
touch backend/tests/test_retriever.py
touch backend/tests/test_api.py

touch backend/requirements.txt
touch backend/Dockerfile
touch backend/.env.example
touch backend/.env

# ---------- FRONTEND ----------
mkdir -p frontend/public
mkdir -p frontend/src/components/ChatBox
mkdir -p frontend/src/components/DependencyGraph
mkdir -p frontend/src/components/RepoImportForm
mkdir -p frontend/src/components/CitationCard
mkdir -p frontend/src/components/Layout
mkdir -p frontend/src/components/common
mkdir -p frontend/src/pages
mkdir -p frontend/src/api
mkdir -p frontend/src/hooks
mkdir -p frontend/src/context
mkdir -p frontend/src/styles
mkdir -p frontend/src/utils

touch frontend/src/components/ChatBox/ChatBox.jsx
touch frontend/src/components/ChatBox/ChatMessage.jsx
touch frontend/src/components/ChatBox/ChatInput.jsx

touch frontend/src/components/DependencyGraph/DependencyGraph.jsx
touch frontend/src/components/DependencyGraph/GraphNode.jsx
touch frontend/src/components/DependencyGraph/graphConfig.js

touch frontend/src/components/RepoImportForm/RepoImportForm.jsx
touch frontend/src/components/CitationCard/CitationCard.jsx

touch frontend/src/components/Layout/Navbar.jsx
touch frontend/src/components/Layout/Sidebar.jsx
touch frontend/src/components/Layout/Footer.jsx

touch frontend/src/components/common/Button.jsx
touch frontend/src/components/common/Loader.jsx
touch frontend/src/components/common/ErrorMessage.jsx

touch frontend/src/pages/Home.jsx
touch frontend/src/pages/RepoDashboard.jsx
touch frontend/src/pages/NotFound.jsx

touch frontend/src/api/client.js
touch frontend/src/api/repoApi.js
touch frontend/src/api/queryApi.js
touch frontend/src/api/graphApi.js

touch frontend/src/hooks/useRepoStatus.js
touch frontend/src/hooks/useChat.js

touch frontend/src/context/RepoContext.jsx

touch frontend/src/styles/global.css
touch frontend/src/styles/variables.css

touch frontend/src/utils/formatters.js

touch frontend/src/App.jsx
touch frontend/src/index.js
touch frontend/src/routes.jsx

touch frontend/.env
touch frontend/.env.example
touch frontend/Dockerfile

# ---------- DATA ----------
mkdir -p data/repos
mkdir -p data/vector_store
touch data/.gitkeep

# ---------- DOCS ----------
mkdir -p docs
touch docs/architecture.md
touch docs/setup.md

# ---------- GITHUB ACTIONS ----------
mkdir -p .github/workflows
touch .github/workflows/ci.yml

# ---------- ROOT FILES ----------
touch docker-compose.yml
touch .gitignore
touch LICENSE
touch README.md

echo "Folder structure created successfully."
echo "Next steps:"
echo "  1. cd backend && python3 -m venv venv"
echo "  2. source venv/bin/activate"
echo "  3. pip install -r requirements.txt (after we populate it)"