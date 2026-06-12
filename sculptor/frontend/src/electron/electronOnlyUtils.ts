import getPort from "get-port";

// Use a single source of truth for the port
export const PORT = process.env.SCULPTOR_API_PORT
  ? Promise.resolve(Number(process.env.SCULPTOR_API_PORT))
  : getPort({ host: "127.0.0.1" });
