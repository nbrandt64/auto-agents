import { getDb } from "./db";

const db = getDb();

const tasks = [
  { title: "Set up project structure", description: "Create frontend, api, and data directories", assignee: "Web", status: "done" },
  { title: "Design task schema", description: "SQLite table for tasks with status, assignee", assignee: "Data", status: "done" },
  { title: "Build REST API", description: "CRUD endpoints for /tasks", assignee: "API", status: "in_progress" },
  { title: "Create TaskBoard component", description: "Display tasks grouped by status", assignee: "Web", status: "todo" },
  { title: "Add filtering", description: "Filter tasks by status and assignee", assignee: "Web", status: "todo" },
];

const stmt = db.prepare(
  "INSERT INTO tasks (title, description, assignee, status) VALUES (?, ?, ?, ?)"
);

for (const t of tasks) {
  stmt.run(t.title, t.description, t.assignee, t.status);
}

console.log(`Seeded ${tasks.length} tasks.`);
