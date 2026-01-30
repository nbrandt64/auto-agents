import express from "express";
import cors from "cors";
import { taskRoutes } from "./routes/tasks";

const app = express();
const PORT = process.env.PORT || 3001;

app.use(cors());
app.use(express.json());

app.use("/tasks", taskRoutes);

app.get("/health", (_req, res) => {
  res.json({ status: "ok" });
});

app.listen(PORT, () => {
  console.log(`TaskFlow API running on http://localhost:${PORT}`);
});
