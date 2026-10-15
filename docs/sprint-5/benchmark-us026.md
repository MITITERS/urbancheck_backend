# Detección de duplicados con volumen (US-026, escenario 9)

- Reportes cargados: 100000 (70% cerrados, 6 categorías, recuadro de ~10 km), en 6.2 s
- Búsquedas: 300, con duplicado en 27
- Tiempo por búsqueda: promedio 1.34 ms · mediana 1.20 ms · p95 2.06 ms · máximo 5.19 ms
- Usa el índice `report_duplicate_lookup`: sí

## Plan de una búsqueda (EXPLAIN ANALYZE)

```
Limit  (cost=9.06..9.07 rows=1 width=216) (actual time=0.009..0.009 rows=0.00 loops=1)
  Buffers: shared hit=3
  ->  Sort  (cost=9.06..9.07 rows=1 width=216) (actual time=0.009..0.009 rows=0.00 loops=1)
        Sort Key: ((acos(LEAST(GREATEST(((('0.8442287804702499'::double precision * cos(radians((latitude)::double precision))) * cos((radians((longitude)::double precision) - '-1.1038090508142857'::double precision))) + ('-0.5359829906123091'::double precision * sin(radians((latitude)::double precision)))), '-1'::double precision), '1'::double precision)) * '6371000'::double precision)), created_at
        Sort Method: quicksort  Memory: 25kB
        Buffers: shared hit=3
        ->  Index Scan using report_duplicate_lookup on reports_report  (cost=0.41..9.05 rows=1 width=216) (actual time=0.008..0.008 rows=0.00 loops=1)
              Index Cond: ((municipality_id = 12) AND ((category)::text = 'bache'::text) AND (latitude >= '-32.4108695'::numeric) AND (latitude <= '-32.4103305'::numeric) AND (longitude >= '-63.2439192'::numeric) AND (longitude <= '-63.2432808'::numeric))
              Filter: ((photo_removed_at IS NULL) AND ((acos(LEAST(GREATEST(((('0.8442287804702499'::double precision * cos(radians((latitude)::double precision))) * cos((radians((longitude)::double precision) - '-1.1038090508142857'::double precision))) + ('-0.5359829906123091'::double precision * sin(radians((latitude)::double precision)))), '-1'::double precision), '1'::double precision)) * '6371000'::double precision) <= '30'::double precision))
              Index Searches: 1
              Buffers: shared hit=3
Planning Time: 0.063 ms
Execution Time: 0.021 ms
```

Todo lo cargado se revirtió al terminar.
