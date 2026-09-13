{% test observed_at_is_plausible(model, column_name='observed_at') %}
{#
  Catches a unit error at the point it would otherwise become data.

  adsb.lol reports the response instant in milliseconds while the per-aircraft ages in the same
  document are in seconds. Mixing them yields timestamps tens of thousands of years out, and
  nothing further down the pipeline would object — the rows would simply never intersect any
  time window the UI asks for, and the layer would look empty for a reason no one could see.
#}

select {{ column_name }}
from {{ model }}
where
    {{ column_name }} < timestamptz '2020-01-01 00:00:00+00'
    or {{ column_name }} > now() + interval '1 day'

{% endtest %}


{% test position_is_in_aoi(model, lon_column='lon', lat_column='lat') %}
{#
  The AOI clip is what bounds the artifact size, so a position outside it means the clip was
  bypassed rather than that an aircraft strayed.
#}

select {{ lon_column }}, {{ lat_column }}
from {{ model }}
where not ({{ nightfall.in_aoi(lon_column, lat_column) }})

{% endtest %}


{% test fraction_between_zero_and_one(model, column_name) %}

select {{ column_name }}
from {{ model }}
where {{ column_name }} < 0.0 or {{ column_name }} > 1.0

{% endtest %}
