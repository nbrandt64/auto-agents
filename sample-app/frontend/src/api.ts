import type { Task, CreateTaskInput, UpdateTaskInput, ApiResponse } from "../../shared/types";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:3001";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `HTTP ${res.status}`);
  }
  const json: ApiResponse<T> = await res.json();
  return json.data;
}

export function getTasks(): Promise<Task[]> {
  return request("/tasks");
}

export function createTask(input: CreateTaskInput): Promise<Task> {
  return request("/tasks", { method: "POST", body: JSON.stringify(input) });
}

export function updateTask(id: number, input: UpdateTaskInput): Promise<Task> {
  return request(`/tasks/${id}`, { method: "PATCH", body: JSON.stringify(input) });
}

export function deleteTask(id: number): Promise<void> {
  return request(`/tasks/${id}`, { method: "DELETE" });
}
