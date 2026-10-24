/**
 * Hooks for managing an entity's manual image (Feature 092): upload,
 * switch source, remove.
 *
 * The portrait URL is cache-busted by `entity.image.version`, which is served
 * by the entity-detail query, so a successful upload invalidates it.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
  removeEntityImage,
  setEntityImageSource,
  uploadEntityImage,
  type EntityImageState,
} from "../api/entityMentions";
import type { ApiError } from "../types/video";

/** Mutation: upload (or replace) the entity's manual image. */
export function useUploadEntityImage(entityId: string) {
  const queryClient = useQueryClient();
  return useMutation<EntityImageState, ApiError, File>({
    mutationFn: (file) => uploadEntityImage(entityId, file),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["entity-detail", entityId],
      });
    },
  });
}

/** Mutation: switch between the manual and Wikidata image. */
export function useSetEntityImageSource(entityId: string) {
  const queryClient = useQueryClient();
  return useMutation<EntityImageState, ApiError, EntityImageState["source"]>({
    mutationFn: (source) => setEntityImageSource(entityId, source),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["entity-detail", entityId],
      });
    },
  });
}

/** Mutation: remove the manual image, reverting to the Wikidata image. */
export function useRemoveEntityImage(entityId: string) {
  const queryClient = useQueryClient();
  return useMutation<void, ApiError, void>({
    mutationFn: () => removeEntityImage(entityId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["entity-detail", entityId],
      });
    },
  });
}
