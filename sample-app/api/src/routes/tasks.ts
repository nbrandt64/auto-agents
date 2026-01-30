import { Router } from "express";
import { getAllTasks, getTaskById, insertTask, patchTask, removeTask } from "../../data/src/queries";
import type { CreateTaskInput, UpdateTaskInput } from "../../shared/types";

export const taskRoutes = Router();

taskRoutes.get("/", (_req, res) => {
  const tasks = getAllTasks();
  res.json({ data: tasks });
});

taskRoutes.get("/:id", (req, res) => {
  const task = getTaskById(Number(req.params.id));
  if (!task) {
    res.status(404).json({ error: "Task not found" });
    return;
  }
  res.json({ data: task });
});

taskRoutes.post("/", (req, res) => {
  const input: CreateTaskInput = req.body;
  if (!input.title?.trim()) {
    res.status(400).json({ error: "Title is required" });
    return;
  }
  const task = insertTask(input);
  res.status(201).json({ data: task });
});

taskRoutes.patch("/:id", (req, res) => {
  const input: UpdateTaskInput = req.body;
  const task = patchTask(Number(req.params.id), input);
  if (!task) {
    res.status(404).json({ error: "Task not found" });
    return;
  }
  res.json({ data: task });
});

taskRoutes.delete("/:id", (req, res) => {
  const deleted = removeTask(Number(req.params.id));
  if (!deleted) {
    res.status(404).json({ error: "Task not found" });
    return;
  }
  res.json({ data: null });
});
