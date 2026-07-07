-- Exclude placeholder neighborhoods and invalid prices from neighborhoods_by_filters RPC
-- Context: Production verification of list_neighborhoods tool revealed:
--   - "Sin especificar" appears in 67/1000 active properties (~6.7%), skewing aggregate discovery
--   - No other common placeholders found (N/A, No aplica, -, etc.)
--   - price_cop <= 0 currently absent but guarded against for future-proofing
-- Fix: Case-insensitive filtering + invalid price guard

create or replace function public.neighborhoods_by_filters(
    p_operation_type text default null,
    p_property_type text default null,
    p_min_bedrooms integer default null,
    p_min_bathrooms integer default null,
    p_min_parking integer default null,
    p_min_price_cop bigint default null,
    p_max_price_cop bigint default null,
    p_min_area_m2 numeric default null,
    p_stratum integer default null,
    p_limit integer default 20
)
returns table (
    neighborhood text,
    property_count bigint,
    min_price_cop bigint
) language sql stable as $$
    select
        p.neighborhood,
        count(*) as property_count,
        min(p.price_cop) as min_price_cop
    from public.properties p
    where
        p.is_active = true
        and p.neighborhood is not null
        and lower(trim(p.neighborhood)) not in ('sin especificar')
        and p.price_cop > 0
        and (p_operation_type is null or p.operation_type = p_operation_type)
        and (p_property_type is null or p.property_type = p_property_type)
        and (p_min_bedrooms is null or p.bedrooms >= p_min_bedrooms)
        and (p_min_bathrooms is null or p.bathrooms >= p_min_bathrooms)
        and (p_min_parking is null or p.parking_spots >= p_min_parking)
        and (p_min_price_cop is null or p.price_cop >= p_min_price_cop)
        and (p_max_price_cop is null or p.price_cop <= p_max_price_cop)
        and (p_min_area_m2 is null or p.area_m2 >= p_min_area_m2)
        and (p_stratum is null or p.stratum = p_stratum)
    group by p.neighborhood
    order by property_count desc, min_price_cop asc
    limit least(p_limit, 50);
$$ security invoker;

-- Note: CREATE OR REPLACE FUNCTION with the same signature (matching parameter types and
-- return table) automatically preserves existing GRANT statements in PostgreSQL — no need
-- to re-run GRANT EXECUTE. The permission on the RPC remains valid for role 'anon'.
