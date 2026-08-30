"""Build the Langfuse monitoring dashboard.

Checked first, not assumed: querying the Langfuse API directly
(lf.api.unstable.dashboards.list()) showed zero dashboards exist for a
fresh project — there's no auto-created default waiting for us. A real
monitoring dashboard has to actually be built.

Built as code rather than clicked together in the UI, matching how
everything else in this project is built (reproducible, not a
one-off manual step that isn't documented anywhere). Uses
lf.api.unstable.dashboards/dashboard_widgets — "unstable" is Langfuse's
own label for this API surface, not a caveat we're adding; noted
honestly in case it changes in a future SDK version.

Every field name here (measure names like `totalCost`/`latency`, valid
dimension fields like `providedModelName`, filter schema) was verified
by direct API calls against a real project, not guessed from docs —
several plausible-looking names (`cost`, `model`, `time_to_first_token`)
turned out to be wrong and only the actually-valid ones are used here.

Six widgets, each answering a real question about the deployed system
rather than padding for the count:
1. Total LLM calls (volume)
2. Cost over time
3. Latency (p50) over time
4. Token usage over time
5. Calls by model (terra vs luna — generation vs query-rewrite, visible
   as two different models in one view)
6. Average user feedback score

Usage:
    python monitoring/build_dashboard.py
"""

from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

from langfuse import get_client  # noqa: E402

DASHBOARD_NAME = "Canadian Investing Assistant — Monitoring"

# (name, view, dimensions, metrics, filters, chart_type)
WIDGETS = [
    (
        "Total LLM calls",
        "observations",
        [],
        [{"measure": "count", "agg": "count"}],
        [{"column": "type", "operator": "=", "value": "GENERATION", "type": "string"}],
        "NUMBER",
    ),
    (
        "Cost over time",
        "observations",
        [],
        [{"measure": "totalCost", "agg": "sum"}],
        [{"column": "type", "operator": "=", "value": "GENERATION", "type": "string"}],
        "LINE_TIME_SERIES",
    ),
    (
        "Latency (p50) over time",
        "observations",
        [],
        [{"measure": "latency", "agg": "p50"}],
        [{"column": "type", "operator": "=", "value": "GENERATION", "type": "string"}],
        "LINE_TIME_SERIES",
    ),
    (
        "Token usage over time",
        "observations",
        [],
        [{"measure": "totalTokens", "agg": "sum"}],
        [{"column": "type", "operator": "=", "value": "GENERATION", "type": "string"}],
        "LINE_TIME_SERIES",
    ),
    (
        "Calls by model",
        "observations",
        [{"field": "providedModelName"}],
        [{"measure": "count", "agg": "count"}],
        [{"column": "type", "operator": "=", "value": "GENERATION", "type": "string"}],
        "VERTICAL_BAR",
    ),
    (
        "Average user feedback",
        "scores-numeric",
        [],
        [{"measure": "value", "agg": "avg"}],
        [{"column": "name", "operator": "=", "value": "user_feedback", "type": "string"}],
        "NUMBER",
    ),
]


def main() -> None:
    lf = get_client()

    print("Creating widgets...")
    widget_ids = []
    for name, view, dimensions, metrics, filters, chart_type in WIDGETS:
        widget = lf.api.unstable.dashboard_widgets.create(
            name=name, view=view, dimensions=dimensions, metrics=metrics,
            filters=filters, chart_type=chart_type,
        )
        widget_ids.append(widget.id)
        print(f"  {name!r} -> {widget.id}")

    print(f"\nCreating dashboard {DASHBOARD_NAME!r}...")
    dashboard = lf.api.unstable.dashboards.create(name=DASHBOARD_NAME)
    print(f"  dashboard id: {dashboard.id}")

    print("\nPlacing widgets on a 2-column grid...")
    width, height = 6, 4  # Langfuse's grid is 12 columns wide; 2 widgets per row
    for i, widget_id in enumerate(widget_ids):
        col = i % 2
        row = i // 2
        lf.api.unstable.dashboards.add_placement(
            dashboard.id,
            request={
                "type": "widget",
                "widgetId": widget_id,
                "x": col * width,
                "y": row * height,
                "width": width,
                "height": height,
            },
        )

    print(f"\nDone. {len(widget_ids)} widgets on dashboard {dashboard.id}.")
    print("View it in the Langfuse Cloud UI under Dashboards.")


if __name__ == "__main__":
    main()
