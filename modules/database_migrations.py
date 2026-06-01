"""
Database Migration Functions

Handles schema updates and data migrations for the Supervertaler database.
"""

import sqlite3
from typing import Optional


def migrate_termbase_fields(db_manager) -> bool:
    """
    Migrate termbase_terms table to add new fields:
    - project (TEXT)
    - client (TEXT)
    - term_uuid (TEXT UNIQUE) - for tracking terms across import/export
    
    Note: 'notes' field already exists in schema, 'definition' is legacy (no longer used)
    
    Args:
        db_manager: DatabaseManager instance
        
    Returns:
        True if migration successful
    """
    try:
        cursor = db_manager.cursor
        
        # Check which columns exist
        cursor.execute("PRAGMA table_info(termbase_terms)")
        columns = {row[1] for row in cursor.fetchall()}
        
        migrations_needed = []
        
        # Add 'project' column if it doesn't exist
        if 'project' not in columns:
            migrations_needed.append(("project", "ALTER TABLE termbase_terms ADD COLUMN project TEXT"))
        
        # Add 'client' column if it doesn't exist
        if 'client' not in columns:
            migrations_needed.append(("client", "ALTER TABLE termbase_terms ADD COLUMN client TEXT"))
        
        # Add 'term_uuid' column if it doesn't exist
        # Note: SQLite doesn't allow adding UNIQUE constraint via ALTER TABLE,
        # so we add column first, then create unique index separately
        if 'term_uuid' not in columns:
            migrations_needed.append(("term_uuid", "ALTER TABLE termbase_terms ADD COLUMN term_uuid TEXT"))
        
        # Add 'note' column if it doesn't exist (legacy, kept for compatibility)
        if 'note' not in columns:
            migrations_needed.append(("note", "ALTER TABLE termbase_terms ADD COLUMN note TEXT"))
        
        # Add 'notes' column if it doesn't exist (used by termbase entry editor)
        if 'notes' not in columns:
            migrations_needed.append(("notes", "ALTER TABLE termbase_terms ADD COLUMN notes TEXT"))

        # Add 'is_nontranslatable' column if it doesn't exist (v1.9.393).
        # Mirrors the schema the Trados plugin already maintains, so flags
        # set in either product are visible to the other against a shared DB.
        if 'is_nontranslatable' not in columns:
            migrations_needed.append((
                "is_nontranslatable",
                "ALTER TABLE termbase_terms ADD COLUMN is_nontranslatable BOOLEAN DEFAULT 0",
            ))
        
        # Execute migrations
        for column_name, sql in migrations_needed:
            print(f"📊 Adding column '{column_name}' to termbase_terms...")
            cursor.execute(sql)
            print(f"  ✓ Column '{column_name}' added successfully")
        
        # Create UNIQUE index for term_uuid if column was added
        if 'term_uuid' in [name for name, _ in migrations_needed]:
            print("📊 Creating UNIQUE index for term_uuid...")
            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_termbase_term_uuid 
                ON termbase_terms(term_uuid)
            """)
            print("  ✓ UNIQUE index created successfully")
        
        db_manager.connection.commit()
        
        if migrations_needed:
            print(f"✅ Database migration completed: {len(migrations_needed)} column(s) added")
        else:
            print("✅ Database schema is up to date")
        
        return True
        
    except Exception as e:
        print(f"❌ Database migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def create_synonyms_table(db_manager) -> bool:
    """
    Create termbase_synonyms table for storing term synonyms.
    
    Schema:
    - id: Primary key
    - term_id: Foreign key to termbase_terms
    - synonym_text: The synonym text
    - language: 'source' or 'target'
    - created_date: Timestamp
    
    Args:
        db_manager: DatabaseManager instance
        
    Returns:
        True if successful
    """
    try:
        cursor = db_manager.cursor
        
        # Check if table already exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='termbase_synonyms'
        """)
        
        if cursor.fetchone():
            print("✅ termbase_synonyms table already exists")
            return True
        
        print("📊 Creating termbase_synonyms table...")
        
        cursor.execute("""
            CREATE TABLE termbase_synonyms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                term_id INTEGER NOT NULL,
                synonym_text TEXT NOT NULL,
                language TEXT NOT NULL CHECK(language IN ('source', 'target')),
                display_order INTEGER DEFAULT 0,
                forbidden INTEGER DEFAULT 0,
                created_date TEXT DEFAULT (datetime('now')),
                modified_date TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (term_id) REFERENCES termbase_terms(id) ON DELETE CASCADE
            )
        """)
        
        # Create indexes for fast lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_synonyms_term_id 
            ON termbase_synonyms(term_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_synonyms_text 
            ON termbase_synonyms(synonym_text)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_synonyms_language 
            ON termbase_synonyms(language)
        """)
        
        db_manager.connection.commit()
        print("✅ termbase_synonyms table created successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to create termbase_synonyms table: {e}")
        import traceback
        traceback.print_exc()
        return False


def migrate_tm_activation_column_name(db_manager) -> bool:
    """Rename tm_activation.tm_id -> tm_db_id (idempotent).

    The column holds the NUMERIC translation_memories.id, but its old name
    collided with translation_units.tm_id (the string slug) — the confusion
    behind the v1.10.242 "0 TM matches" bug. Renaming makes the schema
    self-documenting. ALTER ... RENAME COLUMN rewrites the PK + FK definitions
    automatically.
    """
    try:
        cursor = db_manager.cursor
        cols = [r[1] for r in cursor.execute("PRAGMA table_info(tm_activation)")]
        if 'tm_db_id' in cols or 'tm_id' not in cols:
            return True  # already migrated (or table absent)
        cursor.execute("ALTER TABLE tm_activation RENAME COLUMN tm_id TO tm_db_id")
        db_manager.connection.commit()
        print("✓ Renamed tm_activation.tm_id -> tm_db_id")
        return True
    except Exception as e:
        print(f"✗ tm_activation column rename failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def migrate_termbase_terms_id_to_integer(db_manager) -> bool:
    """Rebuild termbase_terms so termbase_id has INTEGER affinity (was TEXT),
    removing the TEXT-vs-INTEGER mismatch that forced CASTs in every join.
    Idempotent. Preserves all rows + the `id` PK (FTS content_rowid and the
    termbase_synonyms FK depend on it), recreates indexes, rebuilds FTS.
    Validated on a real 93k-row copy before shipping.
    """
    try:
        cursor = db_manager.cursor
        info = {r[1]: (r[2] or '') for r in cursor.execute("PRAGMA table_info(termbase_terms)")}
        if not info or info.get('termbase_id', '').upper() == 'INTEGER':
            return True  # already migrated (or table absent)

        row = cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='termbase_terms'").fetchone()
        if not row:
            return True
        new_sql = row[0].replace("CREATE TABLE termbase_terms (",
                                 "CREATE TABLE termbase_terms_new (", 1)
        new_sql = new_sql.replace("termbase_id TEXT NOT NULL",
                                  "termbase_id INTEGER NOT NULL", 1)
        if "termbase_terms_new" not in new_sql or "termbase_id INTEGER NOT NULL" not in new_sql:
            print("✗ termbase_terms migration: unexpected DDL, skipping (no change made)")
            return False
        idx_sqls = [r[0] for r in cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='termbase_terms' "
            "AND sql IS NOT NULL")]

        conn = db_manager.connection
        old_iso = conn.isolation_level
        conn.isolation_level = None  # manage the transaction explicitly
        try:
            cursor.execute("PRAGMA foreign_keys=OFF")
            cursor.execute("BEGIN")
            cursor.execute(new_sql)
            cursor.execute("INSERT INTO termbase_terms_new SELECT * FROM termbase_terms")
            cursor.execute("DROP TABLE termbase_terms")
            cursor.execute("ALTER TABLE termbase_terms_new RENAME TO termbase_terms")
            for s in idx_sqls:
                cursor.execute(s)
            cursor.execute("INSERT OR REPLACE INTO sqlite_sequence(name, seq) "
                           "SELECT 'termbase_terms', COALESCE(MAX(id), 0) FROM termbase_terms")
            cursor.execute("INSERT INTO termbase_terms_fts(termbase_terms_fts) VALUES('rebuild')")
            cursor.execute("COMMIT")
        except Exception:
            try:
                cursor.execute("ROLLBACK")
            except Exception:
                pass
            raise
        finally:
            cursor.execute("PRAGMA foreign_keys=ON")
            conn.isolation_level = old_iso

        viol = cursor.execute("PRAGMA foreign_key_check").fetchall()
        if viol:
            print(f"⚠️ termbase_terms migration: {len(viol)} FK violation(s) after rebuild")
        print("✓ Rebuilt termbase_terms with INTEGER termbase_id")
        return True
    except Exception as e:
        print(f"✗ termbase_terms INTEGER migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_migrations(db_manager) -> bool:
    """
    Run all pending database migrations.

    Args:
        db_manager: DatabaseManager instance

    Returns:
        True if all migrations successful
    """
    print("\n" + "="*60)
    print("DATABASE MIGRATIONS")
    print("="*60)

    success = True

    # Migration 1: Add new termbase fields
    if not migrate_termbase_fields(db_manager):
        success = False

    # Migration 2: Create synonyms table
    if not create_synonyms_table(db_manager):
        success = False

    # Migration 3: Add display_order and forbidden fields to synonyms
    if not migrate_synonym_fields(db_manager):
        success = False

    # Migration 4: Add ai_inject field to termbases
    if not migrate_termbase_ai_inject(db_manager):
        success = False

    # Migration 5: Create clipboard_history table
    if not create_clipboard_history_table(db_manager):
        success = False

    # Migration 6: Disambiguate tm_activation.tm_id (numeric id) -> tm_db_id
    if not migrate_tm_activation_column_name(db_manager):
        success = False

    # Migration 7: termbase_terms.termbase_id TEXT -> INTEGER. MUST run last —
    # it rebuilds the table, so it needs every column added by earlier
    # migrations to already be present.
    if not migrate_termbase_terms_id_to_integer(db_manager):
        success = False

    print("="*60)

    return success


def check_and_migrate(db_manager) -> bool:
    """
    Check if migrations are needed and run them if so.
    This is safe to call on every app startup.
    
    Args:
        db_manager: DatabaseManager instance
        
    Returns:
        True if migrations successful or not needed
    """
    try:
        print("🔍 Checking database schema for migrations...")
        cursor = db_manager.cursor
        
        # Quick check: do we need migrations?
        cursor.execute("PRAGMA table_info(termbase_terms)")
        columns = {row[1] for row in cursor.fetchall()}
        print(f"🔍 Found termbase_terms columns: {sorted(columns)}")
        
        needs_migration = (
            'project' not in columns or 
            'client' not in columns or
            'term_uuid' not in columns or
            'note' not in columns
        )
        
        # Check if synonyms table exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='termbase_synonyms'
        """)
        needs_synonyms_table = cursor.fetchone() is None

        # Check if termbases table has ai_inject column
        cursor.execute("PRAGMA table_info(termbases)")
        termbase_columns = {row[1] for row in cursor.fetchall()}
        needs_ai_inject = 'ai_inject' not in termbase_columns

        # Check if clipboard_history table exists, OR if it lacks the image columns
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='clipboard_history'
        """)
        clipboard_exists = cursor.fetchone() is not None
        needs_clipboard_table = not clipboard_exists
        if clipboard_exists:
            cursor.execute("PRAGMA table_info(clipboard_history)")
            cb_cols = {row[1] for row in cursor.fetchall()}
            if 'kind' not in cb_cols or 'image_data' not in cb_cols:
                needs_clipboard_table = True
                print("⚠️ Migration needed - clipboard_history image columns missing")
        elif needs_clipboard_table:
            print("⚠️ Migration needed - clipboard_history table missing")

        if needs_migration:
            print(f"⚠️ Migration needed - missing columns: {', '.join([c for c in ['project', 'client', 'term_uuid', 'note'] if c not in columns])}")

        if needs_synonyms_table:
            print("⚠️ Migration needed - termbase_synonyms table missing")

        if needs_ai_inject:
            print("⚠️ Migration needed - termbases.ai_inject column missing")

        # Identifier-disambiguation migrations (2026-06-01):
        # tm_activation.tm_id -> tm_db_id, and termbase_terms.termbase_id TEXT -> INTEGER.
        cursor.execute("PRAGMA table_info(tm_activation)")
        tma_cols = {row[1] for row in cursor.fetchall()}
        needs_tm_activation_rename = ('tm_id' in tma_cols and 'tm_db_id' not in tma_cols)
        if needs_tm_activation_rename:
            print("⚠️ Migration needed - tm_activation.tm_id -> tm_db_id")

        cursor.execute("PRAGMA table_info(termbase_terms)")
        tt_info = {row[1]: (row[2] or '') for row in cursor.fetchall()}
        needs_termbase_id_int = bool(tt_info) and tt_info.get('termbase_id', '').upper() != 'INTEGER'
        if needs_termbase_id_int:
            print("⚠️ Migration needed - termbase_terms.termbase_id TEXT -> INTEGER")

        if (needs_migration or needs_synonyms_table or needs_ai_inject or needs_clipboard_table
                or needs_tm_activation_rename or needs_termbase_id_int):
            success = run_all_migrations(db_manager)
            if success:
                # Generate UUIDs for terms that don't have them
                generate_missing_uuids(db_manager)
            return success
        
        # Even if no schema migration needed, check for missing UUIDs
        print("✅ Database schema is current - checking UUIDs...")
        generate_missing_uuids(db_manager)

        # Fix project termbase flags if needed
        fix_project_termbase_flags(db_manager)

        return True
        
    except Exception as e:
        print(f"❌ Migration check failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def migrate_synonym_fields(db_manager) -> bool:
    """
    Migrate termbase_synonyms table to add new fields:
    - display_order (INTEGER) - position in synonym list (0 = main term)
    - forbidden (INTEGER) - whether this synonym is forbidden (0/1)
    
    Args:
        db_manager: DatabaseManager instance
        
    Returns:
        True if migration successful
    """
    try:
        cursor = db_manager.cursor
        
        # Check if table exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='termbase_synonyms'
        """)
        
        if not cursor.fetchone():
            print("ℹ️ termbase_synonyms table doesn't exist yet - will be created with new schema")
            return True
        
        # Check which columns exist
        cursor.execute("PRAGMA table_info(termbase_synonyms)")
        columns = {row[1] for row in cursor.fetchall()}
        
        migrations_needed = []
        
        # Add 'display_order' column if it doesn't exist
        if 'display_order' not in columns:
            migrations_needed.append(("display_order", "ALTER TABLE termbase_synonyms ADD COLUMN display_order INTEGER DEFAULT 0"))
        
        # Add 'forbidden' column if it doesn't exist
        if 'forbidden' not in columns:
            migrations_needed.append(("forbidden", "ALTER TABLE termbase_synonyms ADD COLUMN forbidden INTEGER DEFAULT 0"))
        
        # Execute migrations
        for column_name, sql in migrations_needed:
            print(f"📊 Adding column '{column_name}' to termbase_synonyms...")
            cursor.execute(sql)
            print(f"  ✓ Column '{column_name}' added successfully")
        
        db_manager.connection.commit()
        
        if migrations_needed:
            print(f"✅ Synonym table migration completed: {len(migrations_needed)} column(s) added")
        else:
            print("✅ Synonym table schema is up to date")
        
        return True
        
    except Exception as e:
        print(f"❌ Synonym table migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def migrate_termbase_ai_inject(db_manager) -> bool:
    """
    Add ai_inject column to termbases table.
    When enabled, the termbase's terms will be injected into LLM translation prompts.

    Args:
        db_manager: DatabaseManager instance

    Returns:
        True if migration successful
    """
    try:
        cursor = db_manager.cursor

        # Check which columns exist
        cursor.execute("PRAGMA table_info(termbases)")
        columns = {row[1] for row in cursor.fetchall()}

        if 'ai_inject' not in columns:
            print("📊 Adding 'ai_inject' column to termbases...")
            cursor.execute("ALTER TABLE termbases ADD COLUMN ai_inject BOOLEAN DEFAULT 0")
            db_manager.connection.commit()
            print("  ✓ Column 'ai_inject' added successfully")
        else:
            print("✅ termbases.ai_inject column already exists")

        return True

    except Exception as e:
        print(f"❌ ai_inject migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def create_clipboard_history_table(db_manager) -> bool:
    """
    Create the clipboard_history table if it does not already exist, and
    add image-support columns if they're missing on an existing table.

    Schema:
    - id         INTEGER PRIMARY KEY AUTOINCREMENT
    - text       TEXT                     – display text or label (e.g. "Image 1920×1080")
    - copied_at  TEXT DEFAULT datetime()  – ISO-8601 timestamp
    - pasted     INTEGER DEFAULT 0        – 1 once the item has been pasted
    - kind       TEXT DEFAULT 'text'      – 'text' or 'image'
    - image_data BLOB                     – PNG bytes for image clips, NULL for text

    Args:
        db_manager: DatabaseManager instance

    Returns:
        True if successful
    """
    try:
        cursor = db_manager.cursor

        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='clipboard_history'
        """)
        table_exists = cursor.fetchone() is not None

        if not table_exists:
            print("📊 Creating clipboard_history table...")
            cursor.execute("""
                CREATE TABLE clipboard_history (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    text       TEXT,
                    copied_at  TEXT    DEFAULT (datetime('now')),
                    pasted     INTEGER DEFAULT 0,
                    kind       TEXT    DEFAULT 'text',
                    image_data BLOB
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_clipboard_id
                ON clipboard_history(id)
            """)
            db_manager.connection.commit()
            print("✅ clipboard_history table created successfully")
            return True

        # Existing table – add new columns if missing
        cursor.execute("PRAGMA table_info(clipboard_history)")
        columns = {row[1] for row in cursor.fetchall()}
        added = []
        if 'kind' not in columns:
            cursor.execute("ALTER TABLE clipboard_history ADD COLUMN kind TEXT DEFAULT 'text'")
            added.append('kind')
        if 'image_data' not in columns:
            cursor.execute("ALTER TABLE clipboard_history ADD COLUMN image_data BLOB")
            added.append('image_data')
        if added:
            db_manager.connection.commit()
            print(f"✅ clipboard_history extended: added {', '.join(added)}")
        else:
            print("✅ clipboard_history table already exists")
        return True

    except Exception as e:
        print(f"❌ Failed to create/migrate clipboard_history table: {e}")
        import traceback
        traceback.print_exc()
        return False


def generate_missing_uuids(db_manager) -> bool:
    """
    Generate UUIDs for any termbase terms that don't have them.
    This ensures all existing terms get UUIDs after the term_uuid column is added.

    Args:
        db_manager: DatabaseManager instance

    Returns:
        True if successful
    """
    try:
        import uuid
        cursor = db_manager.cursor

        # Find terms without UUIDs
        cursor.execute("""
            SELECT id FROM termbase_terms
            WHERE term_uuid IS NULL OR term_uuid = ''
        """)
        terms_without_uuid = cursor.fetchall()

        if not terms_without_uuid:
            return True  # Nothing to do

        print(f"📊 Generating UUIDs for {len(terms_without_uuid)} existing terms...")

        # Generate and assign UUIDs
        for (term_id,) in terms_without_uuid:
            term_uuid = str(uuid.uuid4())
            cursor.execute("""
                UPDATE termbase_terms
                SET term_uuid = ?
                WHERE id = ?
            """, (term_uuid, term_id))

        db_manager.connection.commit()
        print(f"  ✓ Generated {len(terms_without_uuid)} UUIDs successfully")

        return True

    except Exception as e:
        print(f"❌ UUID generation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def fix_project_termbase_flags(db_manager) -> int:
    """
    Fix is_project_termbase flags for termbases that have project_id but is_project_termbase=0.
    This is a data repair function that should be called manually or in migrations.

    Args:
        db_manager: DatabaseManager instance

    Returns:
        Number of termbases fixed
    """
    try:
        cursor = db_manager.cursor

        # Find termbases with project_id but is_project_termbase=0
        cursor.execute("""
            SELECT id, name, project_id
            FROM termbases
            WHERE project_id IS NOT NULL
            AND (is_project_termbase IS NULL OR is_project_termbase = 0)
        """)
        termbases_to_fix = cursor.fetchall()

        if not termbases_to_fix:
            print("✅ All project termbases are correctly flagged")
            return 0

        print(f"📊 Found {len(termbases_to_fix)} termbase(s) that need is_project_termbase flag fix:")
        for tb_id, tb_name, project_id in termbases_to_fix:
            print(f"  - ID {tb_id}: '{tb_name}' (project_id={project_id})")

        # Fix the flags
        cursor.execute("""
            UPDATE termbases
            SET is_project_termbase = 1
            WHERE project_id IS NOT NULL
            AND (is_project_termbase IS NULL OR is_project_termbase = 0)
        """)

        updated_count = cursor.rowcount
        db_manager.connection.commit()

        print(f"✅ Fixed is_project_termbase flag for {updated_count} termbase(s)")

        return updated_count

    except Exception as e:
        print(f"❌ Failed to fix project termbase flags: {e}")
        import traceback
        traceback.print_exc()
        return 0
