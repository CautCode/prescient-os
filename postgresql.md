# PostgreSQL Migration Plan for Prescient OS

## Overview
This document outlines a phased approach to migrate the Prescient OS trading system from JSON file-based storage to PostgreSQL database. The migration will be done incrementally to minimize risk and maintain system functionality throughout the process.

---

## Quick Start Summary

### Migration Approach: Zero-Downtime Dual-Write Strategy

**Core Principle**: JSON stays as source of truth until PostgreSQL is proven stable.

#### The 3-Step Process:

1. **Parallel Write (Weeks 1-5)**
   - Write to BOTH JSON and PostgreSQL simultaneously
   - JSON remains the primary data source
   - If PostgreSQL fails, system continues normally
   - Gradually add tables: Trades → History → Signals → Markets

2. **Switch Reads (Week 6)**
   - Flip `USE_DATABASE_READ=true` in `.env`
   - Application reads from PostgreSQL, falls back to JSON on error
   - JSON writes continue as backup

3. **Go PostgreSQL-Only (Weeks 7-8)**
   - Remove JSON write operations
   - PostgreSQL becomes primary
   - Archive JSON files for audit trail

#### Why This Works:
- ✅ **Zero risk**: Trading never stops, even if database crashes
- ✅ **Reversible**: Set environment variable to rollback instantly
- ✅ **Testable**: Validate data consistency at every phase
- ✅ **Fast**: Each phase takes 1 week, 8 weeks total

---

### Backup & Recovery Strategy

#### During Migration (Phases 0-6):
**You have double backups automatically!**
- JSON files in `data/` directory (automatic, no action needed)
- PostgreSQL database (set up daily dumps below)

#### Daily PostgreSQL Backups:

**Option 1: Manual Backup (Run daily)**
```bash
# Create backup
pg_dump -U prescient_user -d prescient_os > backups/prescient_os_backup_$(date +%Y%m%d).sql

# Restore from backup (if needed)
psql -U prescient_user -d prescient_os < backups/prescient_os_backup_20251027.sql
```

**Option 2: Automated Backup (Windows Task Scheduler)**
1. Create `scripts/backup_db.bat`:
   ```batch
   @echo off
   set BACKUP_DIR=C:\Users\berar\Desktop\prescient-os\backups
   set PGPASSWORD=YourSecurePassword123!

   "C:\Program Files\PostgreSQL\16\bin\pg_dump.exe" -U prescient_user -d prescient_os > "%BACKUP_DIR%\prescient_os_%date:~-4,4%%date:~-10,2%%date:~-7,2%.sql"

   REM Delete backups older than 30 days
   forfiles /p "%BACKUP_DIR%" /m *.sql /d -30 /c "cmd /c del @path"
   ```

2. Schedule with Task Scheduler:
   - Open Task Scheduler
   - Create Basic Task → Daily at 2 AM
   - Action: Start program → `scripts/backup_db.bat`

**Option 3: Use pgAdmin (GUI)**
- Right-click database → Backup
- Format: Plain
- Filename: `backups/prescient_os_YYYYMMDD.sql`

#### Emergency Restore from JSON (If PostgreSQL Fails):
```bash
# Revert to JSON-only mode
# In .env file:
USE_DATABASE_WRITE=false
USE_DATABASE_READ=false

# System automatically uses JSON files
# No data loss - JSON has all recent data
```

#### Post-Migration Backups (Phase 7+):
```bash
# Full backup (weekly)
pg_dump -U prescient_user -d prescient_os -F c -f backups/full_backup_$(date +%Y%m%d).dump

# Incremental backup (daily)
pg_dump -U prescient_user -d prescient_os > backups/daily_$(date +%Y%m%d).sql

# Export to JSON as fallback (weekly)
python scripts/export_db_to_json.py
```

**Backup Retention Policy**:
- Keep daily backups for 30 days
- Keep weekly backups for 6 months
- Keep JSON export for 90 days post-migration

---

### Best Practices & Pro Tips

#### ✅ DO:
1. **Test PostgreSQL connection BEFORE starting migration**
   ```bash
   python -c "from src.db.connection import test_connection; test_connection()"
   ```

2. **Run Phase 1 for at least 3 days before Phase 2**
   - Verify data consistency between JSON and PostgreSQL
   - Check database performance under load

3. **Monitor disk space**
   - PostgreSQL uses ~2x more space than JSON initially
   - Set up alerts if disk usage > 80%

4. **Keep `.env` variables organized**
   ```bash
   # Start with:
   USE_DATABASE_WRITE=false
   USE_DATABASE_READ=false
   DATABASE_FALLBACK_TO_JSON=true

   # Phase 1-4: Enable writes
   USE_DATABASE_WRITE=true

   # Phase 5: Enable reads
   USE_DATABASE_READ=true

   # Phase 6+: Full PostgreSQL
   DATABASE_FALLBACK_TO_JSON=false
   ```

5. **Take a full backup before each phase**
   ```bash
   # Before Phase 1, 2, 3, etc.
   pg_dump -U prescient_user -d prescient_os > backups/before_phase_X.sql
   ```

#### ❌ DON'T:
1. **Don't skip phases** - Each phase validates the previous one
2. **Don't delete JSON files until Week 8** - They're your safety net
3. **Don't run migration during active trading hours** - Migrate at night or weekends
4. **Don't forget to backup .env file** - Contains database credentials
5. **Don't set `DATABASE_FALLBACK_TO_JSON=false` until Phase 7** - You need the fallback!

#### Performance Tips:
- **Indexes**: Already included in schema for common queries
- **Connection pooling**: Configured in `connection.py` (10 connections)
- **Query optimization**: Use `EXPLAIN ANALYZE` for slow queries
- **Monitor query performance**:
  ```sql
  -- Find slow queries
  SELECT query, mean_exec_time, calls
  FROM pg_stat_statements
  ORDER BY mean_exec_time DESC
  LIMIT 10;
  ```

#### Troubleshooting Quick Reference:
| Problem | Solution |
|---------|----------|
| "psql: command not found" | Add `C:\Program Files\PostgreSQL\16\bin` to PATH |
| "password authentication failed" | Check `.env` password matches PostgreSQL user password |
| "permission denied for schema public" | Run: `GRANT ALL ON SCHEMA public TO prescient_user;` |
| Data inconsistency between JSON/DB | Check logs, re-run dual-write for that table |
| PostgreSQL won't start | Check Windows Services → postgresql-x64-16 |
| Slow queries | Add indexes: see [postgresql.md:862](#L862) for schema |

---

### Migration Checklist

**Before You Start:**
- [ ] Read entire migration plan (30 minutes)
- [ ] PostgreSQL 16 installed and running
- [ ] Database `prescient_os` created
- [ ] User `prescient_user` created with password
- [ ] Python packages installed: `psycopg2-binary sqlalchemy alembic`
- [ ] Connection test passes
- [ ] Backup strategy set up (automated daily dumps)
- [ ] JSON files backed up to external location

**Week-by-Week Validation:**
- [ ] Week 1 (Phase 0): All infrastructure ready, connection works
- [ ] Week 2 (Phase 1): Trades writing to both JSON + PostgreSQL
- [ ] Week 3 (Phase 2): Historical data in sync
- [ ] Week 4 (Phase 3): Signals tracked in database
- [ ] Week 5 (Phase 4): Markets/events stored in database
- [ ] Week 6 (Phase 5): Reading from PostgreSQL, JSON fallback works
- [ ] Week 7 (Phase 6): Writing only to PostgreSQL, system stable
- [ ] Week 8 (Phase 7): JSON code removed, monitoring in place

**Success Criteria:**
- ✅ Zero data loss throughout migration
- ✅ System never goes down during migration
- ✅ Database queries faster than JSON reads
- ✅ Backups tested and working
- ✅ Team comfortable with PostgreSQL operations

---

## Current System Analysis

### Data Storage Patterns
Currently, the system uses JSON files for all data persistence:

1. **Events Data** (`data/events/`)
   - `raw_events_backup.json` - All active events from Polymarket API
   - `filtered_events.json` - Events filtered for trading viability

2. **Markets Data** (`data/markets/`)
   - `filtered_markets.json` - Markets filtered from events with detailed API data

3. **Trading Signals** (`data/trades/`)
   - `current_signals.json` - Current trading signals (OVERWRITE mode)
   - Signal archives in `data/history/signals_archive_YYYY-MM.json` (APPEND mode)

4. **Portfolio & Trades** (`data/trades/`)
   - `portfolio.json` - Current portfolio state (OVERWRITE mode)
   - `paper_trades.json` - Complete trade history (APPEND mode)

5. **Historical Data** (`data/history/`)
   - `portfolio_history.json` - Daily portfolio snapshots (APPEND mode)
   - `signals_archive_YYYY-MM.json` - Monthly signal archives (APPEND mode)

### Key Data Flows
1. Events Controller � Market Controller � Strategy Controller � Paper Trading Controller
2. Trading Controller orchestrates the full cycle
3. Data persistence happens at each stage with JSON files

---

## Migration Strategy: Phased Approach

### Phase 0: Preparation (Week 1)
**Goal**: Set up infrastructure without changing application code

---

#### Step 1: Install PostgreSQL on Windows

##### Option A: Using Official Installer (Recommended for Beginners)

1. **Download PostgreSQL Installer**
   - Go to: https://www.postgresql.org/download/windows/
   - Click "Download the installer" (EnterpriseDB installer)
   - Download the latest version (e.g., PostgreSQL 16.x)
   - File will be named something like: `postgresql-16.x-windows-x64.exe`

2. **Run the Installer**
   - Double-click the downloaded `.exe` file
   - Click "Next" through the welcome screen

3. **Installation Directory**
   - Default: `C:\Program Files\PostgreSQL\16`
   - You can keep the default or change it
   - Click "Next"

4. **Select Components**
   - ✅ PostgreSQL Server (required)
   - ✅ pgAdmin 4 (GUI tool - highly recommended)
   - ✅ Command Line Tools (required)
   - ✅ Stack Builder (optional)
   - Click "Next"

5. **Data Directory**
   - Default: `C:\Program Files\PostgreSQL\16\data`
   - Keep the default
   - Click "Next"

6. **Set PostgreSQL Password** ⚠️ IMPORTANT
   - You'll be asked to set a password for the `postgres` superuser
   - **Write this down!** You'll need it later
   - Example: `PostgreSQL2024!` (use your own secure password)
   - Enter the same password twice
   - Click "Next"

7. **Port**
   - Default: `5432`
   - Keep the default unless you have another PostgreSQL running
   - Click "Next"

8. **Locale**
   - Default: `[Default locale]`
   - Keep the default
   - Click "Next"

9. **Install**
   - Review the summary
   - Click "Next" to begin installation
   - Wait for installation to complete (2-5 minutes)
   - **Uncheck** "Stack Builder" at the end (we don't need it)
   - Click "Finish"

##### Option B: Using Chocolatey (For Advanced Users)

```bash
# Install Chocolatey first if you don't have it
# https://chocolatey.org/install

# Install PostgreSQL
choco install postgresql

# This installs PostgreSQL and sets it up as a Windows service
```

---

#### Step 2: Verify PostgreSQL is Running

1. **Check Windows Services**
   - Press `Win + R`
   - Type `services.msc` and press Enter
   - Look for `postgresql-x64-16` (or similar)
   - Status should be "Running"
   - If not, right-click → Start

2. **Test Command Line Access**
   - Press `Win + R`
   - Type `cmd` and press Enter
   - Run:
   ```bash
   # Check PostgreSQL version
   psql --version

   # Should output something like: psql (PostgreSQL) 16.x
   ```

   If you get "command not found", add to PATH:
   - Search "Environment Variables" in Windows
   - Edit "Path" in System Variables
   - Add: `C:\Program Files\PostgreSQL\16\bin`
   - Restart your terminal

---

#### Step 3: Access PostgreSQL

##### Option A: Using psql (Command Line)

1. **Connect as postgres superuser**
   ```bash
   # Method 1: Using psql directly
   psql -U postgres

   # You'll be prompted for the password you set during installation
   ```

   Or on Windows:
   ```bash
   # Navigate to bin directory
   cd "C:\Program Files\PostgreSQL\16\bin"

   # Connect
   psql.exe -U postgres
   ```

   **Expected Output:**
   ```
   Password for user postgres: [enter your password]
   psql (16.x)
   WARNING: Console code page (437) differs from Windows code page (1252)
            8-bit characters might not work correctly...
   Type "help" for help.

   postgres=#
   ```

##### Option B: Using pgAdmin 4 (GUI - Easier for Beginners)

1. **Launch pgAdmin 4**
   - Search for "pgAdmin 4" in Windows Start Menu
   - Click to open

2. **Set Master Password** (First time only)
   - pgAdmin will ask you to set a master password
   - This is different from your PostgreSQL password
   - This just protects pgAdmin itself

3. **Connect to Server**
   - In the left sidebar, expand "Servers"
   - Click "PostgreSQL 16" (or your version)
   - Enter the **postgres password** you set during installation
   - ✅ Check "Save password"
   - Click "OK"

4. **You're Connected!**
   - You should see:
     - Databases
     - Login/Group Roles
     - Tablespaces

---

#### Step 4: Create the Database and User

##### Option A: Using psql (Command Line)

1. **Connect to PostgreSQL**
   ```bash
   psql -U postgres
   ```

2. **Create the Database**
   ```sql
   -- Create database
   CREATE DATABASE prescient_os;

   -- Output should be: CREATE DATABASE
   ```

3. **Create User**
   ```sql
   -- Create user with password
   CREATE USER prescient_user WITH PASSWORD 'YourSecurePassword123!';

   -- Output should be: CREATE ROLE
   ```

4. **Grant Privileges**
   ```sql
   -- Grant all privileges on the database
   GRANT ALL PRIVILEGES ON DATABASE prescient_os TO prescient_user;

   -- Output should be: GRANT
   ```

5. **Connect to the new database**
   ```sql
   -- Switch to prescient_os database
   \c prescient_os

   -- Output: You are now connected to database "prescient_os" as user "postgres".
   ```

6. **Grant schema privileges** (IMPORTANT - PostgreSQL 15+)
   ```sql
   -- Grant privileges on public schema
   GRANT ALL ON SCHEMA public TO prescient_user;
   GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO prescient_user;
   GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO prescient_user;

   -- Set default privileges for future tables
   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO prescient_user;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO prescient_user;
   ```

7. **Verify User Can Connect**
   ```sql
   -- Exit postgres
   \q
   ```

   ```bash
   # Connect as prescient_user
   psql -U prescient_user -d prescient_os

   # You should be prompted for prescient_user's password
   # If successful, you'll see: prescient_os=>
   ```

8. **List Databases (Verification)**
   ```sql
   -- List all databases
   \l

   -- You should see prescient_os in the list

   -- Exit
   \q
   ```

##### Option B: Using pgAdmin 4 (GUI)

1. **Create Database**
   - In pgAdmin, right-click on "Databases"
   - Select "Create" → "Database..."
   - Database name: `prescient_os`
   - Owner: `postgres` (for now)
   - Click "Save"

2. **Create User**
   - Right-click "Login/Group Roles"
   - Select "Create" → "Login/Group Role..."
   - **General Tab:**
     - Name: `prescient_user`
   - **Definition Tab:**
     - Password: `YourSecurePassword123!`
   - **Privileges Tab:**
     - ✅ Can login?
     - ✅ Can create databases? (optional)
   - Click "Save"

3. **Grant Privileges to User**
   - Right-click on "prescient_os" database
   - Select "Properties"
   - Go to "Security" tab
   - Click "+" to add a privilege
   - Grantee: `prescient_user`
   - Privileges: Select "ALL"
   - Click "Save"

4. **Verify**
   - Right-click "Servers" in sidebar
   - Select "Register" → "Server..."
   - **General Tab:**
     - Name: `Prescient OS (as user)`
   - **Connection Tab:**
     - Host: `localhost`
     - Port: `5432`
     - Database: `prescient_os`
     - Username: `prescient_user`
     - Password: [enter password]
     - ✅ Save password
   - Click "Save"
   - If successful, you'll see the new connection in the sidebar

---

#### Step 5: Create Database Schema

1. **Create schema directory**
   ```bash
   mkdir -p src/db
   ```

2. **Create schema file**
   Create file: `src/db/schema.sql`

   Copy the **entire schema** from the "Detailed Database Schema" section below (starting line 289)

3. **Apply the schema**

   **Option A: Using psql**
   ```bash
   # Navigate to project directory
   cd C:\Users\berar\Desktop\prescient-os

   # Apply schema as prescient_user
   psql -U prescient_user -d prescient_os -f src/db/schema.sql

   # You should see a lot of:
   # CREATE TABLE
   # CREATE INDEX
   # INSERT 0 5
   ```

   **Option B: Using pgAdmin**
   - Connect to `prescient_os` database
   - Click "Tools" → "Query Tool"
   - Open `src/db/schema.sql` in a text editor
   - Copy all the SQL
   - Paste into pgAdmin Query Tool
   - Click "Execute" (play button) or press F5

4. **Verify Tables Were Created**
   ```sql
   -- List all tables
   \dt

   -- You should see:
   -- portfolio_snapshots
   -- portfolio_state
   -- portfolio_positions
   -- trades
   -- trading_signals
   -- ... and more
   ```

---

#### Step 6: Install Python Dependencies

1. **Activate your virtual environment** (if using one)
   ```bash
   # If you have a virtual environment
   venv\Scripts\activate  # Windows
   ```

2. **Install PostgreSQL Python drivers**
   ```bash
   pip install psycopg2-binary sqlalchemy alembic python-dotenv
   ```

   **Expected output:**
   ```
   Collecting psycopg2-binary
     Downloading psycopg2_binary-2.9.x-cp311-cp311-win_amd64.whl
   Collecting sqlalchemy
     Downloading SQLAlchemy-2.0.x-cp311-cp311-win_amd64.whl
   Collecting alembic
     Downloading alembic-1.13.x-py3-none-any.whl
   Successfully installed ...
   ```

3. **Verify installation**
   ```bash
   python -c "import psycopg2; print('psycopg2 version:', psycopg2.__version__)"
   python -c "import sqlalchemy; print('SQLAlchemy version:', sqlalchemy.__version__)"
   ```

---

#### Step 7: Create Database Connection Manager

1. **Create connection file**
   Create file: `src/db/connection.py`

   ```python
   import os
   from sqlalchemy import create_engine, text
   from sqlalchemy.orm import sessionmaker
   from contextlib import contextmanager
   import logging

   logger = logging.getLogger(__name__)

   # Database URL from environment variables
   def get_database_url():
       """Build database URL from environment variables"""
       user = os.getenv('POSTGRES_USER', 'prescient_user')
       password = os.getenv('POSTGRES_PASSWORD')
       host = os.getenv('POSTGRES_HOST', 'localhost')
       port = os.getenv('POSTGRES_PORT', '5432')
       database = os.getenv('POSTGRES_DB', 'prescient_os')

       if not password:
           raise ValueError("POSTGRES_PASSWORD environment variable not set")

       return f"postgresql://{user}:{password}@{host}:{port}/{database}"

   # Create engine with connection pooling
   try:
       DATABASE_URL = get_database_url()
       engine = create_engine(
           DATABASE_URL,
           pool_size=10,
           max_overflow=20,
           pool_pre_ping=True,  # Verify connections before using
           echo=os.getenv('SQL_DEBUG', 'false').lower() == 'true'
       )
       SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
       logger.info("Database engine created successfully")
   except ValueError as e:
       logger.warning(f"Database not configured: {e}")
       engine = None
       SessionLocal = None

   @contextmanager
   def get_db():
       """Database session context manager"""
       if SessionLocal is None:
           raise RuntimeError("Database not configured. Set POSTGRES_PASSWORD in .env file")

       db = SessionLocal()
       try:
           yield db
           db.commit()
       except Exception as e:
           db.rollback()
           logger.error(f"Database error: {e}")
           raise
       finally:
           db.close()

   def test_connection():
       """Test database connectivity"""
       try:
           with get_db() as db:
               result = db.execute(text("SELECT 1"))
               logger.info("Database connection test: SUCCESS")
               return True
       except Exception as e:
           logger.error(f"Database connection test FAILED: {e}")
           return False
   ```

2. **Update `.env` file**
   Add to your `.env` file:
   ```bash
   # PostgreSQL Configuration
   POSTGRES_HOST=localhost
   POSTGRES_PORT=5432
   POSTGRES_DB=prescient_os
   POSTGRES_USER=prescient_user
   POSTGRES_PASSWORD=YourSecurePassword123!

   # Migration Configuration (don't enable yet)
   USE_DATABASE_WRITE=false
   USE_DATABASE_READ=false
   DATABASE_FALLBACK_TO_JSON=true

   # Optional: Enable SQL query logging
   SQL_DEBUG=false
   ```

3. **Test the connection**
   ```bash
   python -c "from src.db.connection import test_connection; test_connection()"

   # Expected output:
   # INFO: Database connection test: SUCCESS
   # True
   ```

   If it fails:
   - Check your password in `.env`
   - Verify PostgreSQL is running
   - Check if prescient_os database exists: `psql -U postgres -l`

---

#### Step 8: Set Up Alembic for Migrations (Optional for Phase 0)

1. **Initialize Alembic**
   ```bash
   alembic init alembic
   ```

   This creates:
   - `alembic/` directory
   - `alembic.ini` file

2. **Configure Alembic**
   Edit `alembic.ini`:
   ```ini
   # Find this line:
   sqlalchemy.url = driver://user:pass@localhost/dbname

   # Comment it out and leave blank (we'll use env variables):
   # sqlalchemy.url =
   ```

   Edit `alembic/env.py`:
   ```python
   # Add at the top
   import os
   from dotenv import load_dotenv

   load_dotenv()

   # Find this section and modify:
   def get_url():
       user = os.getenv('POSTGRES_USER')
       password = os.getenv('POSTGRES_PASSWORD')
       host = os.getenv('POSTGRES_HOST')
       port = os.getenv('POSTGRES_PORT')
       database = os.getenv('POSTGRES_DB')
       return f"postgresql://{user}:{password}@{host}:{port}/{database}"

   # In run_migrations_offline():
   context.configure(
       url=get_url(),
       target_metadata=target_metadata,
       literal_binds=True,
       dialect_opts={"paramstyle": "named"},
   )

   # In run_migrations_online():
   configuration = config.get_section(config.config_ini_section)
   configuration['sqlalchemy.url'] = get_url()
   connectable = engine_from_config(...)
   ```

---

#### Step 9: Verification Checklist

Run these commands to verify everything is set up:

```bash
# 1. PostgreSQL is installed
psql --version

# 2. PostgreSQL service is running
# (Windows) Check services.msc

# 3. Can connect as postgres superuser
psql -U postgres -c "SELECT version();"

# 4. Database exists
psql -U postgres -l | grep prescient_os

# 5. User exists and can connect
psql -U prescient_user -d prescient_os -c "SELECT current_user;"

# 6. Tables exist
psql -U prescient_user -d prescient_os -c "\dt"

# 7. Python packages installed
pip list | grep -E "psycopg2|sqlalchemy|alembic"

# 8. Python can connect
python -c "from src.db.connection import test_connection; print(test_connection())"
```

**All checks should pass!**

---

#### Troubleshooting

##### Issue: "psql: command not found"
**Solution**: Add PostgreSQL to PATH
- Windows: Add `C:\Program Files\PostgreSQL\16\bin` to System PATH
- Restart terminal

##### Issue: "password authentication failed for user"
**Solution**:
- Check password in `.env` matches what you set during installation
- Try resetting password:
  ```sql
  psql -U postgres
  ALTER USER prescient_user WITH PASSWORD 'NewPassword123!';
  ```

##### Issue: "database 'prescient_os' does not exist"
**Solution**: Create it
```sql
psql -U postgres
CREATE DATABASE prescient_os;
GRANT ALL PRIVILEGES ON DATABASE prescient_os TO prescient_user;
```

##### Issue: "permission denied for schema public"
**Solution**: Grant schema permissions (PostgreSQL 15+)
```sql
psql -U postgres -d prescient_os
GRANT ALL ON SCHEMA public TO prescient_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO prescient_user;
```

##### Issue: Python can't import psycopg2
**Solution**:
```bash
pip uninstall psycopg2 psycopg2-binary
pip install psycopg2-binary
```

---

#### Deliverables Checklist:
- [ ] PostgreSQL installed and running as Windows service
- [ ] Can connect with: `psql -U postgres`
- [ ] Database `prescient_os` created
- [ ] User `prescient_user` created with password
- [ ] Schema applied (all tables created)
- [ ] Python packages installed (`psycopg2-binary`, `sqlalchemy`, `alembic`)
- [ ] `src/db/connection.py` created
- [ ] `.env` file configured with database credentials
- [ ] Python connection test passes
- [ ] pgAdmin 4 installed and can connect (optional but recommended)

**Time Estimate**: 1-2 hours for first-time setup

---

---

### Phase 1: Parallel Write - Trades & Portfolio (Week 2)
**Goal**: Start writing to PostgreSQL alongside JSON files, with zero risk

#### Why Start Here:
- Trade history and portfolio are the most critical data (business value)
- APPEND-only pattern for trades makes migration safer
- Portfolio is single-record, simple to sync
- No impact on data pipeline if database fails (JSON is still primary)

#### Implementation:

1. **Modify `paper_trading_controller.py`**
   - Add database operations alongside existing JSON operations
   - If database write fails, log error but continue (JSON is still source of truth)
   - Functions to modify:
     - `save_portfolio()` - Write to both JSON and DB
     - `append_trade_to_history()` - Write to both JSON and DB
     - `load_portfolio()` - Still read from JSON (for now)

2. **Tables Involved:**
   ```sql
   - portfolio_snapshots (timestamped portfolio states)
   - trades (all executed trades)
   ```

3. **Testing:**
   - Run full trading cycle
   - Verify data appears in both JSON and PostgreSQL
   - Verify system works even if database is offline

#### Success Criteria:
- Trades written to both JSON and PostgreSQL
- Portfolio updates written to both locations
- System continues working if database fails
- 100% data consistency between JSON and DB

---

### Phase 2: Parallel Write - Historical Data (Week 3)
**Goal**: Add historical tracking to PostgreSQL

#### Implementation:

1. **Modify `trading_controller.py`**
   - `create_daily_portfolio_snapshot()` - Write to both JSON and DB
   - `archive_current_signals()` - Write to both JSON and DB

2. **Tables Involved:**
   ```sql
   - portfolio_history (daily snapshots)
   - signal_archives (monthly signal archives)
   ```

3. **Backfill Historical Data (Optional):**
   ```python
   # Script: scripts/backfill_history.py
   # Read existing JSON history files and import to PostgreSQL
   ```

#### Success Criteria:
- Historical data written to both locations
- Backfill script successfully imports existing history
- No performance degradation

---

### Phase 3: Parallel Write - Trading Signals (Week 4)
**Goal**: Migrate current trading signals to database

#### Implementation:

1. **Modify `trading_strategy_controller.py`**
   - `generate_signals()` - Write signals to both JSON and DB
   - Keep JSON as primary read source for now

2. **Tables Involved:**
   ```sql
   - trading_signals (current signals with metadata)
   ```

3. **Add Signal Lifecycle Tracking:**
   - Track when signals are generated
   - Track when signals are executed
   - Link signals to executed trades

#### Success Criteria:
- Signals written to both JSON and PostgreSQL
- Signal-to-trade linkage working
- Signal history queryable in database

---

### Phase 4: Parallel Write - Markets & Events (Week 5)
**Goal**: Store filtered markets and events in database

#### Why Last for Writes:
- Largest data volume
- Frequently overwritten (less critical to persist long-term)
- Primary value is in the current state, not history

#### Implementation:

1. **Modify `market_controller.py`**
   - `export_filtered_markets_json()` - Write to both JSON and DB
   - Store market snapshots with timestamps

2. **Modify `events_controller.py`**
   - `export_all_active_events_json()` - Write to both JSON and DB (optional)
   - `filter_trading_candidates_json()` - Write to both JSON and DB

3. **Tables Involved:**
   ```sql
   - events (filtered events)
   - markets (filtered markets with metadata)
   - market_snapshots (time-series market data)
   ```

4. **Optimization Considerations:**
   - Events and markets have large payloads
   - Consider storing full JSON in JSONB column vs normalized tables
   - Add indexes on frequently queried fields (market_id, event_id, liquidity, volume)

#### Success Criteria:
- Markets and events written to both locations
- Time-series market data captured
- Query performance acceptable (<100ms for common queries)

---

### Phase 5: Switch to Database Reads (Week 6)
**Goal**: Gradually shift from reading JSON to reading PostgreSQL

#### Approach (Per Controller):
1. Add feature flag: `USE_DATABASE_READ = os.getenv('USE_DATABASE_READ', 'false').lower() == 'true'`
2. Modify load functions to check flag:
   ```python
   if USE_DATABASE_READ:
       return load_from_database()
   else:
       return load_from_json()
   ```
3. Test with flag enabled
4. Once stable, make database the default, keep JSON as fallback

#### Implementation Order:
1. **Portfolio reads** (most critical, single record, simple)
2. **Trade history reads** (read-only, append-only, safe)
3. **Signal reads** (current signals, small dataset)
4. **Market/Event reads** (largest dataset, test performance)

#### Success Criteria:
- All controllers successfully read from database
- Performance meets or exceeds JSON reads
- Fallback to JSON works if database unavailable

---

### Phase 6: Remove JSON Writes (Week 7)
**Goal**: Clean up dual-write code, make PostgreSQL primary

#### Implementation:
1. Remove JSON write operations (keep read as backup)
2. Update all controllers to only write to database
3. Add comprehensive error handling
4. Add database health checks to `/trading/status` endpoint

#### Migration Safety Net:
- Keep JSON read capability for 2 weeks as emergency fallback
- Create database backup script that exports to JSON format
- Monitor system stability

#### Success Criteria:
- Only writing to PostgreSQL
- System stable for 1 week
- Backup/restore procedures tested
- Database monitoring in place

---

### Phase 7: Deprecate JSON Storage (Week 8)
**Goal**: Fully commit to PostgreSQL, remove legacy code

#### Implementation:
1. Remove all JSON read/write code
2. Remove `data/` directory references
3. Update documentation
4. Archive existing JSON files for audit trail

#### Success Criteria:
- Zero JSON file operations in codebase
- All data flows through PostgreSQL
- Documentation updated
- Legacy data archived

---

## Detailed Database Schema

### Core Tables

```sql
-- Portfolio Management
CREATE TABLE portfolio_snapshots (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    balance DECIMAL(15, 2) NOT NULL,
    total_invested DECIMAL(15, 2) NOT NULL,
    total_profit_loss DECIMAL(15, 2) NOT NULL,
    trade_count INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_portfolio_snapshots_timestamp ON portfolio_snapshots(timestamp DESC);

-- Current portfolio state (single row, updated)
CREATE TABLE portfolio_state (
    id INTEGER PRIMARY KEY DEFAULT 1,
    balance DECIMAL(15, 2) NOT NULL,
    total_invested DECIMAL(15, 2) NOT NULL,
    total_profit_loss DECIMAL(15, 2) NOT NULL,
    trade_count INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL,
    last_updated TIMESTAMP NOT NULL,
    CONSTRAINT single_portfolio CHECK (id = 1)
);

-- Portfolio positions (open trades)
CREATE TABLE portfolio_positions (
    id SERIAL PRIMARY KEY,
    trade_id VARCHAR(255) UNIQUE NOT NULL,
    market_id VARCHAR(255) NOT NULL,
    market_question TEXT NOT NULL,
    action VARCHAR(50) NOT NULL, -- 'buy_yes' or 'buy_no'
    amount DECIMAL(15, 2) NOT NULL,
    entry_price DECIMAL(10, 6) NOT NULL,
    entry_timestamp TIMESTAMP NOT NULL,
    status VARCHAR(50) NOT NULL, -- 'open', 'closed'
    current_pnl DECIMAL(15, 2),
    realized_pnl DECIMAL(15, 2),
    exit_price DECIMAL(10, 6),
    exit_timestamp TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_positions_market_id ON portfolio_positions(market_id);
CREATE INDEX idx_positions_status ON portfolio_positions(status);

-- Trade History (append-only)
CREATE TABLE trades (
    id SERIAL PRIMARY KEY,
    trade_id VARCHAR(255) UNIQUE NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    market_id VARCHAR(255) NOT NULL,
    market_question TEXT NOT NULL,
    action VARCHAR(50) NOT NULL,
    amount DECIMAL(15, 2) NOT NULL,
    entry_price DECIMAL(10, 6) NOT NULL,
    confidence DECIMAL(5, 4) NOT NULL,
    reason TEXT,
    status VARCHAR(50) NOT NULL,
    event_id VARCHAR(255),
    event_title TEXT,
    event_end_date TIMESTAMP,
    current_pnl DECIMAL(15, 2),
    realized_pnl DECIMAL(15, 2),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_trades_market_id ON trades(market_id);
CREATE INDEX idx_trades_timestamp ON trades(timestamp DESC);
CREATE INDEX idx_trades_status ON trades(status);

-- Trading Signals
CREATE TABLE trading_signals (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    market_id VARCHAR(255) NOT NULL,
    market_question TEXT NOT NULL,
    action VARCHAR(50) NOT NULL,
    target_price DECIMAL(10, 6) NOT NULL,
    amount DECIMAL(15, 2) NOT NULL,
    confidence DECIMAL(5, 4) NOT NULL,
    reason TEXT,
    yes_price DECIMAL(10, 6) NOT NULL,
    no_price DECIMAL(10, 6) NOT NULL,
    market_liquidity DECIMAL(15, 2),
    market_volume DECIMAL(15, 2),
    event_id VARCHAR(255),
    event_title TEXT,
    event_end_date TIMESTAMP,
    executed BOOLEAN DEFAULT FALSE,
    executed_at TIMESTAMP,
    trade_id VARCHAR(255) REFERENCES trades(trade_id),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_signals_market_id ON trading_signals(market_id);
CREATE INDEX idx_signals_timestamp ON trading_signals(timestamp DESC);
CREATE INDEX idx_signals_executed ON trading_signals(executed);

-- Signal Archives (monthly archives)
CREATE TABLE signal_archives (
    id SERIAL PRIMARY KEY,
    archived_at TIMESTAMP NOT NULL,
    archive_month VARCHAR(7) NOT NULL, -- 'YYYY-MM'
    signals_count INTEGER NOT NULL,
    signals_data JSONB NOT NULL, -- Store full signals array
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_signal_archives_month ON signal_archives(archive_month);

-- Events (filtered events)
CREATE TABLE events (
    id SERIAL PRIMARY KEY,
    event_id VARCHAR(255) UNIQUE NOT NULL,
    title TEXT NOT NULL,
    slug VARCHAR(500),
    liquidity DECIMAL(15, 2),
    volume DECIMAL(15, 2),
    volume24hr DECIMAL(15, 2),
    start_date TIMESTAMP,
    end_date TIMESTAMP,
    days_until_end INTEGER,
    event_data JSONB NOT NULL, -- Store full event JSON
    is_filtered BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_events_event_id ON events(event_id);
CREATE INDEX idx_events_liquidity ON events(liquidity);
CREATE INDEX idx_events_volume ON events(volume);
CREATE INDEX idx_events_end_date ON events(end_date);

-- Markets (filtered markets)
CREATE TABLE markets (
    id SERIAL PRIMARY KEY,
    market_id VARCHAR(255) UNIQUE NOT NULL,
    question TEXT NOT NULL,
    event_id VARCHAR(255),
    event_title TEXT,
    event_end_date TIMESTAMP,
    liquidity DECIMAL(15, 2),
    volume DECIMAL(15, 2),
    volume24hr DECIMAL(15, 2),
    yes_price DECIMAL(10, 6),
    no_price DECIMAL(10, 6),
    market_conviction DECIMAL(10, 6),
    market_data JSONB NOT NULL, -- Store full market JSON
    is_filtered BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_markets_market_id ON markets(market_id);
CREATE INDEX idx_markets_event_id ON markets(event_id);
CREATE INDEX idx_markets_liquidity ON markets(liquidity);
CREATE INDEX idx_markets_volume ON markets(volume);

-- Market Snapshots (time-series market data)
CREATE TABLE market_snapshots (
    id SERIAL PRIMARY KEY,
    market_id VARCHAR(255) NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    yes_price DECIMAL(10, 6),
    no_price DECIMAL(10, 6),
    liquidity DECIMAL(15, 2),
    volume DECIMAL(15, 2),
    volume24hr DECIMAL(15, 2),
    market_conviction DECIMAL(10, 6),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_market_snapshots_market_id ON market_snapshots(market_id);
CREATE INDEX idx_market_snapshots_timestamp ON market_snapshots(timestamp DESC);

-- Portfolio History (daily snapshots)
CREATE TABLE portfolio_history (
    id SERIAL PRIMARY KEY,
    snapshot_date DATE NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    balance DECIMAL(15, 2) NOT NULL,
    total_invested DECIMAL(15, 2) NOT NULL,
    total_profit_loss DECIMAL(15, 2) NOT NULL,
    total_value DECIMAL(15, 2) NOT NULL,
    open_positions INTEGER NOT NULL,
    trade_count INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_portfolio_history_date ON portfolio_history(snapshot_date DESC);

-- System Metadata
CREATE TABLE system_metadata (
    key VARCHAR(255) PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Insert initial metadata
INSERT INTO system_metadata (key, value) VALUES
    ('schema_version', '1.0.0'),
    ('last_event_export', ''),
    ('last_market_filter', ''),
    ('last_signal_generation', ''),
    ('last_trade_execution', '');
```

---

## Database Connection Configuration

### Environment Variables (`.env`)
```bash
# PostgreSQL Configuration
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=prescient_os
POSTGRES_USER=prescient_user
POSTGRES_PASSWORD=your_secure_password

# Migration Configuration
USE_DATABASE_WRITE=true
USE_DATABASE_READ=false  # Start with false, flip to true in Phase 5
DATABASE_FALLBACK_TO_JSON=true  # Keep true until Phase 7
```

### Connection Manager (`src/db/connection.py`)
```python
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)

# Database URL
DATABASE_URL = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"

# Create engine with connection pooling
engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Verify connections before using
    echo=os.getenv('SQL_DEBUG', 'false').lower() == 'true'
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@contextmanager
def get_db():
    """Database session context manager"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        db.close()

def test_connection():
    """Test database connectivity"""
    try:
        with get_db() as db:
            db.execute("SELECT 1")
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False
```

---

## Migration Helpers

### Dual-Write Helper (`src/db/dual_write.py`)
```python
import json
import os
from typing import Any, Callable
import logging

logger = logging.getLogger(__name__)

USE_DATABASE_WRITE = os.getenv('USE_DATABASE_WRITE', 'false').lower() == 'true'
USE_DATABASE_READ = os.getenv('USE_DATABASE_READ', 'false').lower() == 'true'

def dual_write(json_func: Callable, db_func: Callable, *args, **kwargs) -> Any:
    """
    Execute both JSON and database writes during migration phase

    Args:
        json_func: Function to write to JSON
        db_func: Function to write to database
        *args, **kwargs: Arguments for both functions

    Returns:
        Result from JSON function (primary during migration)
    """
    # Always write to JSON (primary during phases 1-5)
    json_result = json_func(*args, **kwargs)

    # Attempt database write if enabled
    if USE_DATABASE_WRITE:
        try:
            db_func(*args, **kwargs)
            logger.debug("Successfully wrote to database")
        except Exception as e:
            logger.error(f"Database write failed (non-fatal): {e}")
            # Don't raise - JSON is still source of truth

    return json_result

def dual_read(json_func: Callable, db_func: Callable, *args, **kwargs) -> Any:
    """
    Read from database or JSON based on configuration

    Args:
        json_func: Function to read from JSON
        db_func: Function to read from database
        *args, **kwargs: Arguments for both functions

    Returns:
        Data from configured source
    """
    if USE_DATABASE_READ:
        try:
            return db_func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Database read failed, falling back to JSON: {e}")
            return json_func(*args, **kwargs)
    else:
        return json_func(*args, **kwargs)
```

---

## Testing Strategy

### Phase-by-Phase Testing

1. **Phase 0**: Database connection test
   ```bash
   python -c "from src.db.connection import test_connection; print(test_connection())"
   ```

2. **Phases 1-4**: Data consistency tests
   ```python
   # scripts/test_data_consistency.py
   # Compare JSON vs PostgreSQL data
   # Verify all writes appear in both locations
   ```

3. **Phase 5**: Read performance tests
   ```python
   # scripts/benchmark_reads.py
   # Compare JSON vs PostgreSQL read performance
   ```

4. **Phase 6-7**: System stability tests
   - Run full trading cycle 100 times
   - Verify zero data loss
   - Test failure scenarios (database down, network issues)

---

## Rollback Plan

### Each Phase Has Rollback:
1. **Phases 1-4**: Simply disable `USE_DATABASE_WRITE` environment variable
2. **Phase 5**: Set `USE_DATABASE_READ=false` to revert to JSON reads
3. **Phase 6-7**: Emergency restore from JSON backup files

### Backup Strategy:
- Daily PostgreSQL backups: `pg_dump prescient_os > backup_$(date +%Y%m%d).sql`
- Keep JSON files for 30 days after Phase 7 completion
- Weekly full backup to external storage

---

## Benefits After Migration

### Performance:
-  Faster queries with indexes (especially for analytics)
-  Join operations for complex queries (trades + markets + events)
-  Time-series analysis on market/portfolio data

### Features Enabled:
-  Real-time P&L tracking with market price updates
-  Advanced analytics (win rate, best markets, strategy performance)
-  Historical backtesting against real market data
-  Multi-strategy comparison
-  Trade correlation analysis

### Reliability:
-  ACID transactions (no partial writes)
-  Referential integrity (signals � trades � portfolio)
-  Concurrent access support (future multi-user)
-  Professional backup/restore procedures

### Scalability:
-  Handles millions of trades without performance degradation
-  Efficient storage (no duplicate market data)
-  Query optimization with indexes
-  Prepared for real-money trading scale

---

## Timeline Summary

| Phase | Duration | Risk Level | Effort |
|-------|----------|-----------|--------|
| Phase 0: Preparation | 1 week | Low | Medium |
| Phase 1: Trades & Portfolio | 1 week | Low | Low |
| Phase 2: Historical Data | 1 week | Low | Low |
| Phase 3: Trading Signals | 1 week | Low | Medium |
| Phase 4: Markets & Events | 1 week | Medium | Medium |
| Phase 5: Switch to DB Reads | 1 week | Medium | Medium |
| Phase 6: Remove JSON Writes | 1 week | Medium | Low |
| Phase 7: Deprecate JSON | 1 week | Low | Low |
| **Total** | **8 weeks** | | |

---

## Success Metrics

### After Phase 1:
- [ ] 100% of trades written to both JSON and PostgreSQL
- [ ] Zero data inconsistencies

### After Phase 4:
- [ ] All data flows to PostgreSQL
- [ ] System stable with dual-write for 1 week

### After Phase 5:
- [ ] All reads from PostgreSQL
- [ ] Read performance e JSON baseline
- [ ] Zero failed reads

### After Phase 7:
- [ ] No JSON dependencies in code
- [ ] Database backup/restore tested
- [ ] Monitoring dashboards operational
- [ ] Team trained on PostgreSQL operations

---

## Next Steps

1. **Review this plan** with the team
2. **Set up development database** (Phase 0)
3. **Create database models and schema** (Phase 0)
4. **Begin Phase 1** implementation with trades & portfolio
5. **Monitor and iterate** based on learnings

---

## Notes & Considerations

### Why This Approach Works:
-  **Low risk**: JSON remains source of truth until Phase 6
-  **Incremental**: Each phase adds value independently
-  **Reversible**: Easy rollback at any stage
-  **Testable**: Can validate at each step
-  **Business continuity**: Trading never stops

### Alternative Approaches Considered:
- L **Big-bang migration**: Too risky, all-or-nothing
- L **Database-first**: Breaks system if database fails
- L **Dual-primary**: Complex conflict resolution

### Critical Success Factors:
1. **Always prioritize data integrity** over speed
2. **Monitor database performance** from day one
3. **Keep JSON fallback** until 100% confident
4. **Test failure scenarios** at each phase
5. **Document all schema changes** with Alembic

---

*Last Updated: 2025-10-27*
*Version: 1.0*
