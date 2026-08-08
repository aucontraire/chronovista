import { defineConfig } from "orval";

export default defineConfig({
  chronovista: {
    input: {
      target: "../contracts/openapi.json",
    },
    output: {
      mode: "tags-split",
      // Generated output is kept in its own directory. The modules directly
      // under src/api (config, settings, onboarding, batchCorrections,
      // entityMentions, overview) are HAND-WRITTEN and tracked in git —
      // generating into that directory would put orval's file management in
      // charge of files it did not create.
      target: "./src/api/generated",
      schemas: "./src/api/generated/models",
      client: "react-query",
      httpClient: "fetch",
      // `clean` deletes everything in `target` that this run did not produce.
      // Scoped to the generated directory that is correct; pointed at src/api
      // it would delete the entire hand-written client.
      clean: true,
      prettier: true,
    },
    hooks: {
      afterAllFilesWrite: "prettier --write",
    },
  },
});
