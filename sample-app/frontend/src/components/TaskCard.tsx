import type { Task } from "../../../shared/types";
import { updateTask, deleteTask } from "../api";

interface Props {
  task: Task;
  onUpdate: () => void;
}

const STATUS_COLORS: Record<Task["status"], string> = {
  todo: "bg-gray-100 text-gray-700",
  in_progress: "bg-yellow-100 text-yellow-800",
  done: "bg-green-100 text-green-800",
};

const NEXT_STATUS: Record<Task["status"], Task["status"]> = {
  todo: "in_progress",
  in_progress: "done",
  done: "todo",
};

export function TaskCard({ task, onUpdate }: Props) {
  const handleStatusChange = async () => {
    await updateTask(task.id, { status: NEXT_STATUS[task.status] });
    onUpdate();
  };

  const handleDelete = async () => {
    await deleteTask(task.id);
    onUpdate();
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 flex items-center gap-4">
      <button
        onClick={handleStatusChange}
        className={`px-2 py-1 rounded text-xs font-medium ${STATUS_COLORS[task.status]}`}
      >
        {task.status === "in_progress" ? "In Progress" : task.status.charAt(0).toUpperCase() + task.status.slice(1)}
      </button>

      <div className="flex-1 min-w-0">
        <h3 className="font-medium text-gray-900 truncate">{task.title}</h3>
        {task.description && (
          <p className="text-sm text-gray-500 truncate">{task.description}</p>
        )}
      </div>

      {task.assignee && (
        <span className="text-sm text-gray-400">{task.assignee}</span>
      )}

      <button onClick={handleDelete} className="text-gray-300 hover:text-red-500 text-sm">
        Delete
      </button>
    </div>
  );
}
