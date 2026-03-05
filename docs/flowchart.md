graph TB
    %% Styling Definitions
    classDef mobile fill:#fce4ec,stroke:#E91E63,stroke-width:2px,color:#880E4F
    classDef user fill:#e8f4fd,stroke:#2196F3,stroke-width:2px,color:#1565C0
    classDef server fill:#fff3e0,stroke:#FF9800,stroke-width:2px,color:#E65100
    classDef process fill:#f3e5f5,stroke:#9C27B0,stroke-width:2px,color:#6A1B9A
    classDef hot fill:#fff3e0,stroke:#FF5722,stroke-width:2px,color:#BF360C
    classDef cold fill:#e8f5e9,stroke:#4CAF50,stroke-width:2px,color:#2E7D32
    classDef noco fill:#fff8e1,stroke:#FFC107,stroke-width:2px,color:#F57F17
    classDef archiver fill:#ffecb3,stroke:#FF9800,stroke-width:2px,color:#E65100

    subgraph MOBILE ["📱 Mobile Monitoring"]
        AT_APP["📱 Airtable Mobile App<br/>(monitor recent pushes)"]:::mobile
    end

    subgraph USER ["👤 User Layer"]
        CE["🧩 Chrome Extension<br/>(popup.js)"]:::user
        NOCO["📊 NocoDB<br/>(Full History UI)<br/>Grid · Kanban · Gallery"]:::noco
        TRIAGE["🔍 Triage App<br/>(triage_app.py)"]:::user
    end

    subgraph SERVER ["⚙️ Pipeline Server Layer"]
        PS["🖥️ Pipeline Server<br/>(orchestrator.js)<br/>:3333"]:::server
        ARCH["🔄 Archiver<br/>(archive.py)<br/>cron / manual trigger"]:::archiver
    end

    subgraph PROCESSING ["🔬 Processing Layer"]
        CAP["📸 Capture<br/>(TypeScript/Playwright)"]:::process
        ANA["🧠 Analyzer<br/>(Python/OpenCV/Ollama)"]:::process
        PUB["📤 Publisher<br/>(publish.py)"]:::process
    end

    subgraph HOT ["🔥 Hot Layer — Recent Data"]
        AT[("📋 Airtable (Free Tier)<br/>~1,000 record limit<br/>Latest videos · shots · frames")]:::hot
    end

    subgraph COLD ["🧊 Cold Layer — Full Archive"]
        PG[("🐘 Postgres<br/>Complete History<br/>channels · videos<br/>shots · frames")]:::cold
        R2["☁️ Cloudflare R2<br/>Frame PNGs<br/>Scene Thumbnails"]:::cold
    end

    %% Mobile reads Airtable
    AT_APP -.->|"native mobile views"| AT

    %% Chrome Extension → Server
    CE -->|"POST /api/videos/upsert"| PS

    %% Server orchestrates
    PS -->|"triggers"| CAP
    CAP --> ANA
    ANA --> PUB

    %% Publisher dual-writes
    PUB -->|"pyairtable<br/>(recent records)"| AT
    PUB -->|"SQL insert<br/>(permanent copy)"| PG
    PUB -->|"parallel uploads"| R2

    %% Archiver moves old Airtable → Postgres
    ARCH -->|"1. read old records<br/>(older than N days)"| AT
    ARCH -->|"2. verify exists<br/>3. delete from Airtable"| AT
    ARCH -->|"verify record exists<br/>in Postgres"| PG

    %% NocoDB + Triage read full history
    NOCO -.->|"reads full archive"| PG
    TRIAGE -->|"SQL queries"| PG
