{#
  Shared SQL fragments. Each exists because the same expression is needed in more than one
  model and a divergence between copies would be invisible in the output.
#}

{% macro sql_string_list(values) -%}
[{% for value in values %}'{{ value }}'{{ ", " if not loop.last }}{% endfor %}]
{%- endmacro %}


{% macro object_observed_at(filename_column) -%}
{#
  The landing-zone filename carries the collection instant (`store.object_path`), which is the
  only record of when a sampling window closed. Parsing it here keeps that fact in one place.
#}
timezone(
    'UTC',
    strptime(
        regexp_extract({{ filename_column }}, '([0-9]{8}T[0-9]{6}Z)', 1),
        '%Y%m%dT%H%M%SZ'
    )
)
{%- endmacro %}


{% macro raw_object(filename_column) -%}
regexp_extract({{ filename_column }}, '([^/]+)$', 1)
{%- endmacro %}


{% macro in_aoi(lon_column, lat_column) -%}
{{ lon_column }} between {{ var('aoi_west') }} and {{ var('aoi_east') }}
    and {{ lat_column }} between {{ var('aoi_south') }} and {{ var('aoi_north') }}
{%- endmacro %}


{% macro time_bucket_of(timestamp_column) -%}
time_bucket(interval '{{ var("time_bucket") }}', {{ timestamp_column }})
{%- endmacro %}
