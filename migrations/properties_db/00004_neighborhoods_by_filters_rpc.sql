-- RPC neighborhoods_by_filters: GROUP BY neighborhood aggregation for discovery UX
-- Used by list_neighborhoods tool (app/tools/properties/neighborhoods_tool.py)
-- Unlike search_properties which returns top-15 individual listings,
-- this RPC groups by neighborhood so aggregate questions see all matching neighborhoods.

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

-- Allow anon role to execute this RPC
grant execute on function public.neighborhoods_by_filters(
    text, text, integer, integer, integer, bigint, bigint, numeric, integer, integer
) to anon;

-- Rollback
/*
revoke execute on function public.neighborhoods_by_filters(
    text, text, integer, integer, integer, bigint, bigint, numeric, integer, integer
) from anon;

drop function if exists public.neighborhoods_by_filters(
    text, text, integer, integer, integer, bigint, bigint, numeric, integer, integer
);
*/
