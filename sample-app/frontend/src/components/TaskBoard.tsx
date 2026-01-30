import type { Task } from "../../../shared/types";
import { TaskCard } from "./TaskCard";

interface Props {
  tasks: Task[];
  onUpdate: () => void;
}

export function TaskBoard({ tasks, onUpdate }: Props) {
  if (tasks.length === 0) {
    return (
      <div className="text-center py-12 text-gray-400">
        No tasks yet. Create one to get started.
      </div>
    );
  }

  return (
    <div className="grid gap-3">
      {tasks.map((task) => (
        <TaskCard key={task.id} task={task} onUpdate={onUpdate} />
      ))}
    </div>
  );
}
