CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS habits (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL,
    title TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,
    reminder_time TIME,
    streak INT DEFAULT 0,
    last_completed DATE,
    CONSTRAINT fk_user FOREIGN KEY (user_id)
        REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS habit_logs (
    id SERIAL PRIMARY KEY,
    habit_id INT NOT NULL,
    date DATE NOT NULL,
    completed BOOLEAN DEFAULT TRUE,
    CONSTRAINT fk_habit FOREIGN KEY (habit_id)
        REFERENCES habits(id) ON DELETE CASCADE,
    UNIQUE (habit_id, date)
);
