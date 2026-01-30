import { getDb } from "./db";
import type { Task, CreateTaskInput, UpdateTaskInput } from "../../shared/types";

export function getAllTasks(): Task[] {
  return getDb().prepare("SELECT * FROM tasks ORDER BY created_at DESC").all() as Task[];
}

export function getTaskById(id: number): Task | undefined {
  return getDb().prepare("SELECT * FROM tasks WHERE id = ?").get(id) as Task | undefined;
}

export function insertTask(input: CreateTaskInput): Task {
  const result = getDb()
    .prepare(
      `INSERT INTO tasks (title, description, assignee, status)
       VALUES (?, ?, ?, 'todo')`
    )
    .run(input.title, input.description || "", input.assignee || null);

  return getTaskById(Number(result.lastInsertRowid))!;
}

export function patchTask(id: number, input: UpdateTaskInput): Task | undefined {
  const existing = getTaskById(id);
  if (!existing) return undefined;

  const fields: string[] = [];
  const values: any[] = [];

  if (input.title !== undefined) { fields.push("title = ?"); values.push(input.title); }
  if (input.description !== undefined) { fields.push("description = ?"); values.push(input.description); }
  if (input.status !== undefined) { fields.push("status = ?"); values.push(input.status); }
  if (input.assignee !== undefined) { fields.push("assignee = ?"); values.push(input.assignee); }

  if (fields.length === 0) return existing;

  fields.push("updated_at = datetime('now')");
  values.push(id);

  getDb().prepare(`UPDATE tasks SET ${fields.join(", ")} WHERE id = ?`).run(...values);
  return getTaskById(id);
}

export function removeTask(id: number): boolean {
  const result = getDb().prepare("DELETE FROM tasks WHERE id = ?").run(id);
  return result.changes > 0;
}
