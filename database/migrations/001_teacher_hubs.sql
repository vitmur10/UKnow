-- Teacher Hub / Forum Topics migration.
-- Run once against school_bot.db before deploying the updated bot.

ALTER TABLE users ADD COLUMN hub_chat_id INTEGER;
ALTER TABLE assignments ADD COLUMN topic_id INTEGER;
ALTER TABLE groups ADD COLUMN topic_id INTEGER;

CREATE INDEX IF NOT EXISTS idx_users_hub_chat_id
    ON users (hub_chat_id);

CREATE INDEX IF NOT EXISTS idx_assignments_topic_id
    ON assignments (topic_id)
    WHERE topic_id IS NOT NULL AND is_active = 1;

CREATE INDEX IF NOT EXISTS idx_groups_topic_id
    ON groups (topic_id)
    WHERE topic_id IS NOT NULL AND is_active = 1;

CREATE UNIQUE INDEX IF NOT EXISTS idx_assignments_active_student_topic
    ON assignments (student_id, topic_id)
    WHERE topic_id IS NOT NULL AND is_active = 1;
