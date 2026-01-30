import type { Request, Response, NextFunction } from "express";

/**
 * Simple API key auth middleware.
 * Set API_KEY env var to enable. If unset, all requests pass through.
 */
export function authMiddleware(req: Request, res: Response, next: NextFunction) {
  const apiKey = process.env.API_KEY;
  if (!apiKey) {
    return next();
  }

  const provided = req.headers["x-api-key"];
  if (provided !== apiKey) {
    return res.status(401).json({ error: "Unauthorized" });
  }

  next();
}
