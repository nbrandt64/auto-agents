export interface Task {
  id: number;
  title: string;
  description: string;
  status: "todo" | "in_progress" | "done";
  assignee: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateTaskInput {
  title: string;
  description?: string;
  assignee?: string;
}

export interface UpdateTaskInput {
  title?: string;
  description?: string;
  status?: Task["status"];
  assignee?: string | null;
}

export interface ApiResponse<T> {
  data: T;
  error?: string;
}
