import { defineConfig } from "orval";

export default defineConfig({
  chronovista: {
    input: {
      target: "../contracts/openapi.json",
    },
    output: {
      mode: "tags-split",
      target: "./src/api",
      schemas: "./src/api/models",
      client: "react-query",
      httpClient: "fetch",
      clean: true,
      prettier: true,
    },
    hooks: {
      afterAllFilesWrite: "prettier --write",
    },
  },
});
