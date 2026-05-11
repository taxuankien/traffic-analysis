import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getConfig,
  putConfig,
  resetConfig,
  getSchema,
  listModels,
  getCatalog,
  downloadModel,
  type InferenceConfig,
} from '../api/inference';

export function useInferenceConfig() {
  const qc = useQueryClient();

  const configQuery = useQuery({
    queryKey: ['inference-config'],
    queryFn: getConfig,
    staleTime: 30_000,
  });

  const schemaQuery = useQuery({
    queryKey: ['inference-schema'],
    queryFn: getSchema,
    staleTime: Infinity,
  });

  const modelsQuery = useQuery({
    queryKey: ['system-models'],
    queryFn: listModels,
    staleTime: 30_000,
  });

  const catalogQuery = useQuery({
    queryKey: ['system-models-catalog'],
    queryFn: getCatalog,
    staleTime: 30_000,
  });

  const saveMutation = useMutation({
    mutationFn: (data: InferenceConfig) => putConfig(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['inference-config'] });
    },
  });

  const resetMutation = useMutation({
    mutationFn: () => resetConfig(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['inference-config'] });
    },
  });

  const downloadMutation = useMutation({
    mutationFn: (modelName: string) => downloadModel(modelName),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['system-models'] });
      qc.invalidateQueries({ queryKey: ['system-models-catalog'] });
    },
  });

  const refetchAll = () => {
    qc.invalidateQueries({ queryKey: ['system-models'] });
    qc.invalidateQueries({ queryKey: ['system-models-catalog'] });
  };

  return {
    config: configQuery.data,
    schema: schemaQuery.data,
    models: modelsQuery.data,
    catalog: catalogQuery.data,
    isLoading: configQuery.isLoading || schemaQuery.isLoading,
    save: saveMutation,
    reset: resetMutation,
    download: downloadMutation,
    refetchModels: refetchAll,
  };
}
