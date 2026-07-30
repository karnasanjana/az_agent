# SchemaViz - ER Diagram Generator

An interactive ER (Entity-Relationship) diagram generator for SQL Server databases. Connect to your database, extract the schema, and visualize table relationships as a fully interactive diagram.

![SchemaViz](https://img.shields.io/badge/version-1.0.0-blue) ![License](https://img.shields.io/badge/license-MIT-green)

## Features

- **Database Connection** - Connect to any SQL Server / Azure SQL database with credential validation
- **Schema Extraction** - Extract tables, columns, primary keys, foreign keys, and indexes with real-time SSE progress streaming
- **Interactive ER Diagram** - Visualize database relationships with draggable table nodes using React Flow
- **Relationship Highlighting** - Hover on edges to highlight connected tables and dim others
- **Cardinality Labels** - Auto-inferred 1:1, 1:N relationship indicators on edges
- **Color-Coded FK Edges** - Each foreign key relationship gets a distinct color
- **Auto Layout** - Dagre-based hierarchical layout with manual repositioning
- **PDF Export** - Export diagrams as PDF with database metadata header
- **Save & Load** - Persist diagrams with positions for later viewing
- **Large Database Support** - Confirmation prompt for 500+ table databases
- **Google OAuth** - Authentication via Auth.js (NextAuth v5)

## Tech Stack

### Frontend
- **Next.js 16** with App Router and Turbopack
- **React 19** with Server Actions
- **React Flow** (`@xyflow/react` v12) for diagram rendering
- **Dagre** for automatic graph layout
- **Tailwind CSS 4** for styling
- **Auth.js v5** (NextAuth) for Google OAuth
- **jsPDF + html-to-image** for PDF export
- **TypeScript 5**

### Backend
- **FastAPI** with async SSE streaming
- **pyodbc** for SQL Server connectivity
- **Pydantic v2** for data validation
- **Fernet encryption** for credential security
- **Uvicorn** ASGI server

## Project Structure

```
ER-Diagram/
├── backend/
│   ├── app/
│   │   ├── api/            # API routes (connection, schema, diagrams)
│   │   ├── database/       # Database connection utilities
│   │   ├── schemas/        # Pydantic models
│   │   ├── security/       # Encryption & logging
│   │   ├── services/       # Schema extraction service
│   │   ├── config.py       # App configuration
│   │   └── main.py         # FastAPI app entry point
│   ├── requirements.txt
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx        # Home - Connection form
│   │   │   ├── extract/        # Schema extraction page
│   │   │   ├── diagram/        # ER diagram viewer
│   │   │   ├── diagrams/       # Saved diagrams list
│   │   │   ├── login/          # Authentication page
│   │   │   └── actions.ts      # Server Actions
│   │   ├── components/
│   │   │   ├── diagram/        # DiagramCanvas, TableNode, RelationshipEdge
│   │   │   ├── connection-form.tsx
│   │   │   └── step-indicator.tsx
│   │   ├── lib/                # Utilities (auth, layout, export, diagram-utils)
│   │   └── types/              # TypeScript type definitions
│   ├── package.json
│   └── next.config.ts
└── .gitignore
```

## Prerequisites

- **Node.js** >= 18
- **Python** >= 3.11
- **ODBC Driver 18 for SQL Server** ([Install guide](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server))

### Install ODBC Driver (macOS)

```bash
brew install unixodbc
brew tap microsoft/mssql-release https://github.com/Microsoft/homebrew-mssql-release
brew install msodbcsql18
```

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/ZionClouds/ER-Diagram.git
cd ER-Diagram
```

### 2. Backend Setup

```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Create environment file
cat > .env << EOF
FERNET_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
API_HOST=0.0.0.0
API_PORT=8000
EOF

# Start the backend server
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`. Swagger docs at `http://localhost:8000/docs`.

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Create environment file
cat > .env.local << EOF
AUTH_SECRET=$(openssl rand -hex 32)
AUTH_GOOGLE_ID=your-google-client-id
AUTH_GOOGLE_SECRET=your-google-client-secret
NEXT_PUBLIC_API_URL=http://localhost:8000
EOF

# Start the development server
npm run dev
```

The app will be available at `http://localhost:3000`.

## Usage

1. **Connect** - Enter your SQL Server credentials (host, port, database, username, password) and test the connection
2. **Extract** - Click "Start Extraction" to extract the database schema with real-time progress
3. **View Diagram** - Interactive ER diagram renders with all tables and foreign key relationships
4. **Interact** - Drag tables, hover edges to highlight relationships, use auto-layout
5. **Export** - Export as PDF or save the diagram for later

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/connection/test` | Test database connection |
| `POST` | `/api/schema/start` | Start schema extraction, returns stream ID |
| `GET` | `/api/schema/stream/{id}` | SSE stream for extraction progress + result |
| `POST` | `/api/schema/confirm/{id}` | Confirm extraction for large databases |
| `GET` | `/api/diagrams` | List saved diagrams |
| `POST` | `/api/diagrams` | Save a diagram |
| `GET` | `/api/diagrams/{id}` | Load a saved diagram |
| `PUT` | `/api/diagrams/{id}` | Update a saved diagram |
| `DELETE` | `/api/diagrams/{id}` | Delete a saved diagram |

## Environment Variables

### Backend (`.env`)
| Variable | Description | Required |
|----------|-------------|----------|
| `FERNET_KEY` | Encryption key for credential security | Yes |
| `API_HOST` | Server host (default: `0.0.0.0`) | No |
| `API_PORT` | Server port (default: `8000`) | No |

### Frontend (`.env.local`)
| Variable | Description | Required |
|----------|-------------|----------|
| `AUTH_SECRET` | NextAuth secret for session encryption | Yes |
| `AUTH_GOOGLE_ID` | Google OAuth client ID | Yes |
| `AUTH_GOOGLE_SECRET` | Google OAuth client secret | Yes |
| `NEXT_PUBLIC_API_URL` | Backend API URL (default: `http://localhost:8000`) | Yes |

## License

MIT
