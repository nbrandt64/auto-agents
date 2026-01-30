import Database from "better-sqlite3";
import path from "path";
import fs from "fs";

const DB_FILE = process.env.DB_PATH || path.join(__dirname, "..", "taskflow.db");

let db: Database.Database;

export function getDb(): Database.Database {
  if (!db) {
    db = new Database(DB_FILE);
    db.pragma("journal_mode = WAL");
    db.pragma("foreign_keys = ON");
    runMigrations(db);
  }
  return db;
}

function runMigrations(database: Database.Database) {
  const migrationsDir = path.join(__dirname, "migrations");
  if (!fs.existsSync(migrationsDir)) return;

  database.exec(`
    CREATE TABLE IF NOT EXISTS _migrations (
      name TEXT PRIMARY KEY,
      applied_at TEXT DEFAULT (datetime('now'))
    )
  `);

  const applied = new Set(
    database.prepare("SELECT name FROM _migrations").all().map((r: any) => r.name)
  );

  const files = fs.readdirSync(migrationsDir).filter((f) => f.endsWith(".sql")).sort();

  for (const file of files) {
    if (applied.has(file)) continue;
    const sql = fs.readFileSync(path.join(migrationsDir, file), "utf-8");
    database.exec(sql);
    database.prepare("INSERT INTO _migrations (name) VALUES (?)").run(file);
    console.log(`Applied migration: ${file}`);
  }
}

// Run migrations if executed directly
if (require.main === module) {
  getDb();
  console.log("Migrations complete.");
}
