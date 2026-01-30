import { useState, useEffect } from "react";
import type { Task } from "../../shared/types";
import { getTasks } from "./api";
import { TaskBoard } from "./components/TaskBoard";
import { TaskForm } from "./components/TaskForm";

export default function App() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [filter, setFilter] = useState<Task["status"] | "all">("all");

  const loadTasks = async () => {
    try {
      const data = await getTasks();
      setTasks(data);
    } catch (err) {
      console.error("Failed to load tasks:", err);
    }
  };

  useEffect(() => {
    loadTasks();
  }, []);

  const filtered = filter === "all" ? tasks : tasks.filter((t) => t.status === filter);

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <h1 className="text-xl font-semibold text-gray-900">TaskFlow</h1>
          <button
            onClick={() => setShowForm(true)}
            className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700"
          >
            New Task
          </button>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-6">
        <div className="flex gap-2 mb-6">
          {(["all", "todo", "in_progress", "done"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={`px-3 py-1 rounded-full text-sm ${
                filter === s ? "bg-blue-100 text-blue-800" : "bg-gray-100 text-gray-600"
              }`}
            >
              {s === "all" ? "All" : s === "in_progress" ? "In Progress" : s.charAt(0).toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>

        <TaskBoard tasks={filtered} onUpdate={loadTasks} />
      </main>

      {showForm && <TaskForm onClose={() => setShowForm(false)} onCreated={loadTasks} />}
    </div>
  );
}
