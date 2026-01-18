-- Database Model Synchronization Migration
-- Adds missing columns and indexes to sync shared/database/models.py
-- Run this ONCE on production database: 66.151.33.167

-- ============================================================================
-- 1. ADD MISSING COLUMNS
-- ============================================================================

-- User table - add extra_data
ALTER TABLE users ADD COLUMN IF NOT EXISTS extra_data JSON;

-- Bot table - add webhook_url and settings
ALTER TABLE bots ADD COLUMN IF NOT EXISTS webhook_url VARCHAR(500);
ALTER TABLE bots ADD COLUMN IF NOT EXISTS settings JSON;

-- AdminUser table - add email and is_superuser
ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS email VARCHAR(255) UNIQUE;
ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS is_superuser BOOLEAN DEFAULT FALSE;

-- ============================================================================
-- 2. ADD MISSING INDEXES
-- ============================================================================

-- BotUser - composite unique index (if not exists)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE indexname = 'ix_bot_users_user_bot'
    ) THEN
        CREATE UNIQUE INDEX ix_bot_users_user_bot ON bot_users(user_id, bot_id);
    END IF;
END
$$;

-- ============================================================================
-- 3. ADD CASCADE DELETE FOR BOT MESSAGES
-- ============================================================================

-- Drop existing constraint (if exists)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'bot_messages_bot_id_fkey'
        AND table_name = 'bot_messages'
    ) THEN
        ALTER TABLE bot_messages DROP CONSTRAINT bot_messages_bot_id_fkey;
    END IF;
END
$$;

-- Add constraint with CASCADE
ALTER TABLE bot_messages
ADD CONSTRAINT bot_messages_bot_id_fkey
FOREIGN KEY (bot_id) REFERENCES bots(id) ON DELETE CASCADE;

-- ============================================================================
-- 4. CREATE BROADCAST TABLES (if not exist)
-- ============================================================================

-- BroadcastStatus enum
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'broadcaststatus') THEN
        CREATE TYPE broadcaststatus AS ENUM ('draft', 'scheduled', 'running', 'completed', 'cancelled');
    END IF;
END
$$;

-- Broadcast table
CREATE TABLE IF NOT EXISTS broadcasts (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    text TEXT NOT NULL,
    image_url VARCHAR(500),
    message_video VARCHAR(500),
    buttons JSON,

    -- Targeting
    target_type VARCHAR(50) DEFAULT 'all',
    target_bots JSON,
    target_languages JSON,
    target_segment_id INTEGER,
    target_user_ids JSON,

    -- Status
    status broadcaststatus DEFAULT 'draft',
    scheduled_at TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,

    -- Stats
    total_recipients INTEGER DEFAULT 0,
    sent_count INTEGER DEFAULT 0,
    delivered_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,

    created_at TIMESTAMP DEFAULT NOW(),
    created_by INTEGER
);

-- BroadcastLog table
CREATE TABLE IF NOT EXISTS broadcast_logs (
    id SERIAL PRIMARY KEY,
    broadcast_id INTEGER NOT NULL REFERENCES broadcasts(id) ON DELETE CASCADE,
    telegram_id BIGINT NOT NULL,
    status VARCHAR(50) NOT NULL,
    error_message TEXT,
    sent_at TIMESTAMP DEFAULT NOW()
);

-- Segment table
CREATE TABLE IF NOT EXISTS segments (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    conditions JSON DEFAULT '{}',
    cached_count INTEGER,
    cached_at TIMESTAMP,
    is_dynamic BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================================
-- 5. UPDATE ENUMS (add new values)
-- ============================================================================

-- UserRole - add MODERATOR
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumlabel = 'moderator'
        AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'userrole')
    ) THEN
        ALTER TYPE userrole ADD VALUE 'moderator';
    END IF;
END
$$;

-- BotStatus - add PAUSED and DISABLED
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumlabel = 'paused'
        AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'botstatus')
    ) THEN
        ALTER TYPE botstatus ADD VALUE 'paused';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumlabel = 'disabled'
        AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'botstatus')
    ) THEN
        ALTER TYPE botstatus ADD VALUE 'disabled';
    END IF;
END
$$;

-- ============================================================================
-- 6. VERIFICATION QUERIES (run after migration)
-- ============================================================================

-- Uncomment to verify after migration:

-- Check new columns exist:
-- SELECT column_name, data_type FROM information_schema.columns
-- WHERE table_name IN ('users', 'bots', 'admin_users')
-- ORDER BY table_name, ordinal_position;

-- Check indexes:
-- SELECT indexname, tablename FROM pg_indexes
-- WHERE tablename IN ('bot_users', 'bot_messages');

-- Check enum values:
-- SELECT enumlabel FROM pg_enum WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'userrole');
-- SELECT enumlabel FROM pg_enum WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'botstatus');

-- Check broadcast tables:
-- SELECT table_name FROM information_schema.tables
-- WHERE table_name IN ('broadcasts', 'broadcast_logs', 'segments');
