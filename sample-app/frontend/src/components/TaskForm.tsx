import { useState } from "react";
import { createTask } from "../api";

interface Props {
  onClose: () => void;
  onCreated: () => void;
}

export function TaskForm({ onClose, onCreated }: Props) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [assignee, setAssignee] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    await createTask({
      title: title.trim(),
      description: description.trim() || undefined,
      assignee: assignee.trim() || undefined,
    });
    onCreated();
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={onClose}>
      <form
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
        className="bg-white rounded-xl shadow-lg p-6 w-full max-w-md"
      >
        <h2 className="text-lg font-semibold mb-4">New Task</h2>

        <label className="block mb-3">
          <span className="text-sm text-gray-600">Title</span>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
            autoFocus
          />
        </label>

        <label className="block mb-3">
          <span className="text-sm text-gray-600">Description</span>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
            rows={3}
          />
        </label>

        <label className="block mb-4">
          <span className="text-sm text-gray-600">Assignee</span>
          <input
            value={assignee}
            onChange={(e) => setAssignee(e.target.value)}
            className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
          />
        </label>

        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-gray-600">
            Cancel
          </button>
          <button
            type="submit"
            className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700"
          >
            Create
          </button>
        </div>
      </form>
    </div>
  );
}
