# migrations/properties_db/

Estas migraciones **no** son parte del esquema de la app (ese vive en
`migrations/*.sql` y se aplica contra el `DATABASE_URL` de este repo).

Son el esquema de búsqueda semántica para `public.properties`, una tabla que
vive en un **proyecto Supabase completamente separado**, dedicado solo a
propiedades de Cali (venta/arriendo), que ya existe y se puebla vía scraper.
La app va a leer de ese proyecto con un cliente Supabase dedicado, usando
anon key (`PROPERTIES_SUPABASE_URL` / `PROPERTIES_SUPABASE_ANON_KEY`), nunca
con las credenciales `SUPABASE_*` ni el `DATABASE_URL` de la app.

El backfill de embeddings (`scripts/backfill_property_embeddings.py`) es el único
proceso que escribe en `property_embeddings`, y por eso usa una tercera credencial de
este mismo proyecto, `PROPERTIES_SUPABASE_SERVICE_ROLE_KEY` (bypasea RLS) — nunca la
anon key de arriba, que solo tiene permiso de lectura (ver
`00003_rls_readonly_anon.sql`).

## Cómo aplicar

Manualmente, en orden, contra el proyecto Supabase de propiedades — nunca
contra el proyecto/DB de la app:

```bash
for f in migrations/properties_db/*.sql; do psql "$PROPERTIES_DATABASE_URL" -f "$f"; done
```

o pegando cada archivo, en orden, en el SQL Editor del dashboard de ese
proyecto Supabase.

Igual que en `migrations/`, nunca modifiques un archivo ya aplicado; los
cambios posteriores van en un archivo nuevo numerado secuencialmente.
