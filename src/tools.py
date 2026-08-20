# ============================================================
# tools.py
# ============================================================

import os
import re
import pandas as pd
from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv()

llm = ChatGroq(
    model="openai/gpt-oss-20b",
    api_key=os.getenv("GROQ_API_KEY"),
    temperature=0
)

STANDARD_TARGETS = [
    "area",
    "resource",
    "needed_quantity",
    "distributed_quantity",
    "quantity_received",
    "date"
]

REQUIRED_NEEDS_COLUMNS = {
    "area",
    "resource",
    "needed_quantity",
    "date"
}

REQUIRED_DISTRIBUTION_COLUMNS = {
    "area",
    "resource",
    "distributed_quantity",
    "date"
}


# ============================================================
# DATE NORMALIZATION
# ============================================================

def normalize_date_value(value):
    if pd.isna(value):
        return pd.NaT

    text = str(value).strip()

    if not text:
        return pd.NaT

    iso_match = re.match(
        r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$",
        text
    )

    if iso_match:
        try:
            return pd.Timestamp(
                year=int(iso_match.group(1)),
                month=int(iso_match.group(2)),
                day=int(iso_match.group(3))
            )
        except ValueError:
            return pd.NaT

    year_month_match = re.match(
        r"^(\d{4})[-/](\d{1,2})$",
        text
    )

    if year_month_match:
        try:
            return pd.Timestamp(
                year=int(year_month_match.group(1)),
                month=int(year_month_match.group(2)),
                day=1
            )
        except ValueError:
            return pd.NaT

    slash_match = re.match(
        r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$",
        text
    )

    if slash_match:
        try:
            return pd.Timestamp(
                year=int(slash_match.group(3)),
                month=int(slash_match.group(1)),
                day=int(slash_match.group(2))
            )
        except ValueError:
            return pd.NaT

    month_name_match = re.match(
        r"^([A-Za-z]{3,9})[\s-]+(\d{4})$",
        text
    )

    if month_name_match:
        parsed = pd.to_datetime(
            f"{month_name_match.group(1)} "
            f"{month_name_match.group(2)}",
            errors="coerce"
        )

        if pd.notna(parsed):
            return pd.Timestamp(
                year=parsed.year,
                month=parsed.month,
                day=1
            )

        return pd.NaT

    parsed = pd.to_datetime(
        text,
        errors="coerce",
        dayfirst=False
    )

    if pd.isna(parsed):
        return pd.NaT

    return pd.Timestamp(parsed)


def normalize_date_column(df):
    df = df.copy()

    if "date" in df.columns:
        df["date"] = df["date"].apply(normalize_date_value)

    return df


# ============================================================
# SCHEMA CLEANING
# ============================================================

def clean_and_map_schema(file_path):

    df = pd.read_csv(file_path)

    column_synonyms = {
        "area": [
            "area",
            "district",
            "location",
            "region"
        ],

        "resource": [
            "resource",
            "commodity",
            "item",
            "resource_type"
        ],

        "needed_quantity": [
            "needed_quantity",
            "needed",
            "required",
            "hh_in_need",
            "demand"
        ],

        "distributed_quantity": [
            "distributed_quantity",
            "distributed",
            "given",
            "allocated",
            "hh_reached"
        ],

        "quantity_received": [
            "quantity_received",
            "donated",
            "received"
        ],

        "date": [
            "date",
            "reporting_period",
            "period",
            "month"
        ]
    }

    column_mapping = {}
    unmapped_columns = []

    for col in df.columns:

        col_clean = (
            str(col)
            .strip()
            .lower()
            .replace(" ", "_")
        )

        matched = False

        for standard_name, variations in column_synonyms.items():

            if col_clean in variations:

                if standard_name not in column_mapping.values():

                    column_mapping[col] = standard_name
                    matched = True

                break

        if not matched:
            unmapped_columns.append(col)

    df = df.rename(columns=column_mapping)

    duplicate_count = int(df.duplicated().sum())

    df = df.drop_duplicates()

    df = normalize_date_column(df)

    missing_values = df.isnull().sum()

    missing_report = (
        missing_values[missing_values > 0]
        .to_dict()
    )

    return {
        "cleaned_data": df,
        "column_mapping": column_mapping,
        "unmapped_columns": unmapped_columns,
        "duplicates_removed": duplicate_count,
        "missing_values": missing_report
    }


# ============================================================
# LLM COLUMN MAPPING
# ============================================================

def llm_map_unmapped_columns(
    df,
    unmapped_columns,
    column_mapping
):

    suggestions = []
    needs_confirmation = []

    already_mapped = list(column_mapping.values())

    derived_keywords = [
        "gap",
        "balance",
        "variance",
        "difference",
        "diff",
        "surplus",
        "shortage",
        "remaining",
        "net"
    ]

    for col in unmapped_columns:

        col_lower = str(col).lower()

        if any(
            keyword in col_lower
            for keyword in derived_keywords
        ):

            needs_confirmation.append({
                "column": col,
                "suggested_as": "none",
                "confidence": "high",
                "reason": (
                    "column name suggests an already-calculated value"
                )
            })

            continue

        sample_values = (
            df[col]
            .dropna()
            .astype(str)
            .unique()[:3]
            .tolist()
        )

        remaining_concepts = [
            target
            for target in STANDARD_TARGETS
            if target not in already_mapped
        ]

        prompt = f"""
You are helping map a column from an NGO dataset.

Standard concepts:

- area = location/district/region
- resource = food, medicine, water, shelter, etc.
- needed_quantity = amount required
- distributed_quantity = amount actually distributed
- quantity_received = amount received by NGO
- date = reporting date or period

Already mapped:
{already_mapped}

Remaining concepts:
{remaining_concepts}

Column:
{col}

Sample values:
{sample_values}

Rules:

1. Do not map calculated gaps.
2. Do not confuse received with distributed.
3. Do not map percentages to quantities.
4. Do not map IDs to area.
5. Do not map monetary values to quantities.
6. Do not map status/metadata.
7. Do not reuse an already mapped concept.
8. If uncertain, return none.

Return ONLY:

concept: <concept or none>
confidence: <high, medium, or low>
"""

        response = llm.invoke(prompt).content.strip()

        concept = "none"
        confidence = "low"

        for line in response.splitlines():

            if line.lower().startswith("concept:"):
                concept = (
                    line.split(":", 1)[1]
                    .strip()
                    .lower()
                )

            elif line.lower().startswith("confidence:"):
                confidence = (
                    line.split(":", 1)[1]
                    .strip()
                    .lower()
                )

        if (
            concept in remaining_concepts
            and confidence == "high"
        ):

            suggestions.append({
                "column": col,
                "suggested_as": concept,
                "confidence": confidence
            })

            already_mapped.append(concept)

        else:

            needs_confirmation.append({
                "column": col,
                "suggested_as": concept,
                "confidence": confidence
            })

    auto_mapped = {
        item["column"]: item
        for item in suggestions
    }

    return {
        "auto_mapped": auto_mapped,
        "needs_user_confirmation": needs_confirmation
    }


# ============================================================
# AGGREGATION
# ============================================================

def aggregate_allocation_data(
    df,
    quantity_column
):

    df = df.copy()

    df[quantity_column] = pd.to_numeric(
        df[quantity_column],
        errors="coerce"
    )

    df[quantity_column] = (
        df[quantity_column]
        .fillna(0)
    )

    df = df.dropna(
        subset=[
            "area",
            "resource",
            "date"
        ]
    )

    grouped = (
        df.groupby(
            [
                "area",
                "resource",
                "date"
            ],
            as_index=False
        )[quantity_column]
        .sum()
    )

    return grouped


# ============================================================
# GAP ANALYSIS - TWO FILES
# ============================================================

def gap_analysis_from_data(
    needs_df,
    distribution_df
):

    needs_df = normalize_date_column(
        needs_df.copy()
    )

    distribution_df = normalize_date_column(
        distribution_df.copy()
    )

    needs_df = aggregate_allocation_data(
        needs_df,
        "needed_quantity"
    )

    distribution_df = aggregate_allocation_data(
        distribution_df,
        "distributed_quantity"
    )

    merged = pd.merge(
        needs_df,
        distribution_df,
        on=[
            "area",
            "resource",
            "date"
        ],
        how="outer"
    )

    merged["needed_quantity"] = (
        pd.to_numeric(
            merged["needed_quantity"],
            errors="coerce"
        )
        .fillna(0)
    )

    merged["distributed_quantity"] = (
        pd.to_numeric(
            merged["distributed_quantity"],
            errors="coerce"
        )
        .fillna(0)
    )

    merged["gap"] = (
        merged["needed_quantity"]
        - merged["distributed_quantity"]
    )

    merged["status"] = merged["gap"].apply(
        lambda gap:
            "Shortage"
            if gap > 0
            else (
                "Surplus"
                if gap < 0
                else "Okay"
            )
    )

    return merged[
        [
            "area",
            "resource",
            "date",
            "needed_quantity",
            "distributed_quantity",
            "gap",
            "status"
        ]
    ].sort_values(
        [
            "area",
            "resource",
            "date"
        ]
    ).reset_index(drop=True)


# ============================================================
# GAP ANALYSIS - COMBINED FILE
# ============================================================

def gap_analysis_from_combined(df):

    df = normalize_date_column(
        df.copy()
    )

    df["needed_quantity"] = (
        pd.to_numeric(
            df["needed_quantity"],
            errors="coerce"
        )
        .fillna(0)
    )

    df["distributed_quantity"] = (
        pd.to_numeric(
            df["distributed_quantity"],
            errors="coerce"
        )
        .fillna(0)
    )

    df = df.dropna(
        subset=[
            "area",
            "resource",
            "date"
        ]
    )

    df = (
        df.groupby(
            [
                "area",
                "resource",
                "date"
            ],
            as_index=False
        )[
            [
                "needed_quantity",
                "distributed_quantity"
            ]
        ]
        .sum()
    )

    df["gap"] = (
        df["needed_quantity"]
        - df["distributed_quantity"]
    )

    df["status"] = df["gap"].apply(
        lambda gap:
            "Shortage"
            if gap > 0
            else (
                "Surplus"
                if gap < 0
                else "Okay"
            )
    )

    return df[
        [
            "area",
            "resource",
            "date",
            "needed_quantity",
            "distributed_quantity",
            "gap",
            "status"
        ]
    ].sort_values(
        [
            "area",
            "resource",
            "date"
        ]
    ).reset_index(drop=True)


def gap_analysis(
    needs_file,
    distribution_file
):

    needs = pd.read_csv(needs_file)
    distribution = pd.read_csv(distribution_file)

    return gap_analysis_from_data(
        needs,
        distribution
    )


# ============================================================
# SINGLE AREA + RESOURCE TREND
# ============================================================

def trend_detection(
    gap_data,
    area,
    resource
):

    subset = gap_data[
        (gap_data["area"] == area)
        &
        (gap_data["resource"] == resource)
    ].copy()

    subset["date"] = (
        subset["date"]
        .apply(normalize_date_value)
    )

    subset = (
        subset
        .dropna(subset=["date"])
        .sort_values("date")
    )

    if subset.empty:

        return {
            "area": area,
            "resource": resource,
            "trend": "no_data",
            "message": (
                f"No data found for "
                f"{resource} in {area}."
            )
        }

    gaps = (
        pd.to_numeric(
            subset["gap"],
            errors="coerce"
        )
        .fillna(0)
        .tolist()
    )

    dates = subset["date"].tolist()

    first_gap = gaps[0]
    last_gap = gaps[-1]

    change = last_gap - first_gap

    if change > 0:
        trend = "worsening"
    elif change < 0:
        trend = "improving"
    else:
        trend = "stable"

    return {
        "area": area,
        "resource": resource,
        "trend": trend,
        "change": change,
        "first_gap": first_gap,
        "last_gap": last_gap,
        "first_date": dates[0],
        "last_date": dates[-1],
        "gap_history": list(zip(dates, gaps)),
        "message": (
            f"{resource} gap in {area} is {trend} "
            f"(gap changed by {change} "
            f"from {first_gap} to {last_gap})."
        )
    }


# ============================================================
# GLOBAL TREND COMPARISON
# ============================================================

def trend_comparison(
    gap_data,
    resource,
    direction="largest"
):

    subset = gap_data[
        gap_data["resource"] == resource
    ].copy()

    subset["date"] = (
        subset["date"]
        .apply(normalize_date_value)
    )

    subset["gap"] = pd.to_numeric(
        subset["gap"],
        errors="coerce"
    )

    subset = subset.dropna(
        subset=[
            "area",
            "date",
            "gap"
        ]
    )

    if subset.empty:

        return {
            "resource": resource,
            "ranking": [],
            "winner": None,
            "message": (
                f"No trend data found for {resource}."
            )
        }

    rows = []

    for area, group in subset.groupby("area"):

        group = group.sort_values("date")

        if len(group) < 2:
            continue

        first = group.iloc[0]
        last = group.iloc[-1]

        first_gap = float(first["gap"])
        last_gap = float(last["gap"])

        change = last_gap - first_gap

        if change > 0:
            trend = "worsening"
        elif change < 0:
            trend = "improving"
        else:
            trend = "stable"

        rows.append({
            "area": area,
            "resource": resource,
            "first_date": first["date"],
            "last_date": last["date"],
            "first_gap": first_gap,
            "last_gap": last_gap,
            "change": change,
            "trend": trend
        })

    if not rows:

        return {
            "resource": resource,
            "ranking": [],
            "winner": None,
            "message": (
                f"Not enough historical data to compare "
                f"{resource} trends across areas."
            )
        }

    ranking = sorted(
        rows,
        key=lambda row: row["change"],
        reverse=(direction == "largest")
    )

    winner = ranking[0]

    direction_text = (
        "biggest increase"
        if direction == "largest"
        else "biggest decrease"
    )

    return {
        "resource": resource,
        "direction": direction,
        "ranking": ranking,
        "winner": winner,
        "message": (
            f"{winner['area']} has the {direction_text} "
            f"in {resource} gap over time: "
            f"{winner['first_gap']} → "
            f"{winner['last_gap']} "
            f"(change={winner['change']})."
        )
    }


# ============================================================
# TREND + CURRENT GAP
# ============================================================

def worsening_current_gap_comparison(
    gap_data,
    resource
):

    subset = gap_data[
        gap_data["resource"] == resource
    ].copy()

    subset["date"] = (
        subset["date"]
        .apply(normalize_date_value)
    )

    subset["gap"] = pd.to_numeric(
        subset["gap"],
        errors="coerce"
    )

    subset = subset.dropna(
        subset=[
            "area",
            "date",
            "gap"
        ]
    )

    if subset.empty:
        return {
            "resource": resource,
            "ranking": [],
            "winner": None,
            "message": (
                f"No data found for {resource}."
            )
        }

    trend_rows = []

    for area, group in subset.groupby("area"):

        group = group.sort_values("date")

        if len(group) < 2:
            continue

        first = group.iloc[0]
        last = group.iloc[-1]

        first_gap = float(first["gap"])
        last_gap = float(last["gap"])

        change = last_gap - first_gap

        # IMPORTANT:
        # worsening means shortage gap increased.
        # We require current shortage as well.
        if (
            change > 0
            and last_gap > 0
        ):

            trend_rows.append({
                "area": area,
                "resource": resource,
                "first_date": first["date"],
                "last_date": last["date"],
                "first_gap": first_gap,
                "last_gap": last_gap,
                "change": change,
                "status": "Shortage"
            })

    if not trend_rows:

        return {
            "resource": resource,
            "ranking": [],
            "winner": None,
            "message": (
                f"No area has a worsening current "
                f"{resource} shortage."
            )
        }

    ranking = sorted(
        trend_rows,
        key=lambda row: row["last_gap"],
        reverse=True
    )

    winner = ranking[0]

    return {
        "resource": resource,
        "ranking": ranking,
        "winner": winner,
        "message": (
            f"{winner['area']} has a worsening "
            f"{resource} shortage and the largest "
            f"current {resource} gap: "
            f"{winner['last_gap']} units. "
            f"The gap increased by {winner['change']} "
            f"units from {winner['first_gap']}."
        )
    }


# ============================================================
# AREA COMPARISON
# ============================================================

def area_comparison(
    gap_data,
    resource,
    date=None
):

    subset = gap_data[
        gap_data["resource"] == resource
    ].copy()

    subset["date"] = (
        subset["date"]
        .apply(normalize_date_value)
    )

    subset = subset.dropna(
        subset=["date"]
    )

    if subset.empty:

        return {
            "resource": resource,
            "date_used": None,
            "ranking": [],
            "message": (
                f"No data found for {resource}."
            )
        }

    date_used = (
        subset["date"].max()
        if date is None
        else normalize_date_value(date)
    )

    subset = subset[
        subset["date"] == date_used
    ]

    if subset.empty:

        return {
            "resource": resource,
            "date_used": None,
            "ranking": [],
            "message": (
                f"No data found for {resource} "
                f"on the requested date."
            )
        }

    subset = (
        subset
        .groupby("area", as_index=False)
        .agg(gap=("gap", "sum"))
    )

    subset["status"] = subset["gap"].apply(
        lambda gap:
            "Shortage"
            if gap > 0
            else (
                "Surplus"
                if gap < 0
                else "Okay"
            )
    )

    ranked = subset.sort_values(
        "gap",
        ascending=False
    )

    ranking = ranked[
        ["area", "gap", "status"]
    ].to_dict("records")

    return {
        "resource": resource,
        "date_used": str(date_used.date()),
        "ranking": ranking,
        "message": (
            f"On {date_used.date()}, "
            f"{ranking[0]['area']} has the largest "
            f"gap for {resource}."
        )
    }


# ============================================================
# RESOURCE COMPARISON
# ============================================================

def resource_comparison(
    gap_data,
    area,
    date=None
):

    subset = gap_data[
        gap_data["area"] == area
    ].copy()

    subset["date"] = (
        subset["date"]
        .apply(normalize_date_value)
    )

    subset = subset.dropna(
        subset=["date"]
    )

    if subset.empty:

        return {
            "area": area,
            "date_used": None,
            "ranking": [],
            "message": (
                f"No data found for {area}."
            )
        }

    date_used = (
        subset["date"].max()
        if date is None
        else normalize_date_value(date)
    )

    subset = subset[
        subset["date"] == date_used
    ]

    if subset.empty:

        return {
            "area": area,
            "date_used": None,
            "ranking": [],
            "message": (
                f"No data found for {area} "
                f"on the requested date."
            )
        }

    subset = (
        subset
        .groupby("resource", as_index=False)
        .agg(gap=("gap", "sum"))
    )

    subset["status"] = subset["gap"].apply(
        lambda gap:
            "Shortage"
            if gap > 0
            else (
                "Surplus"
                if gap < 0
                else "Okay"
            )
    )

    ranked = subset.sort_values(
        "gap",
        ascending=False
    )

    ranking = ranked[
        ["resource", "gap", "status"]
    ].to_dict("records")

    return {
        "area": area,
        "date_used": str(date_used.date()),
        "ranking": ranking,
        "message": (
            f"On {date_used.date()}, "
            f"{ranking[0]['resource']} has the "
            f"largest gap in {area}."
        )
    }


# ============================================================
# PAIRWISE AREA COMPARISON
# ============================================================

def pairwise_area_comparison(
    gap_data,
    area1,
    area2,
    date=None
):

    subset = gap_data[
        gap_data["area"].isin(
            [area1, area2]
        )
    ].copy()

    subset["date"] = (
        subset["date"]
        .apply(normalize_date_value)
    )

    subset["gap"] = pd.to_numeric(
        subset["gap"],
        errors="coerce"
    )

    subset = subset.dropna(
        subset=["date", "gap"]
    )

    if subset.empty:
        return {
            "areas": [area1, area2],
            "winner": None,
            "message": (
                "No matching data was found "
                "for the selected areas."
            )
        }

    date_used = (
        subset["date"].max()
        if date is None
        else normalize_date_value(date)
    )

    subset = subset[
        subset["date"] == date_used
    ]

    if subset.empty:
        return {
            "areas": [area1, area2],
            "winner": None,
            "message": (
                "No matching records were found "
                "on the requested date."
            )
        }

    # --------------------------------------------------------
    # Aggregate by area + resource first
    # --------------------------------------------------------

    resource_gaps = (
        subset
        .groupby(
            ["area", "resource"],
            as_index=False
        )["gap"]
        .sum()
    )

    # --------------------------------------------------------
    # Overall SHORTAGE means only positive gaps.
    # Surpluses do not count as shortage.
    # --------------------------------------------------------

    resource_gaps["shortage"] = (
        resource_gaps["gap"]
        .clip(lower=0)
    )

    totals = (
        resource_gaps
        .groupby("area", as_index=False)
        ["shortage"]
        .sum()
    )

    totals_dict = {
        row["area"]: float(row["shortage"])
        for _, row in totals.iterrows()
    }

    total1 = totals_dict.get(area1, 0.0)
    total2 = totals_dict.get(area2, 0.0)

    if total1 > total2:
        winner = area1
        loser = area2
    elif total2 > total1:
        winner = area2
        loser = area1
    else:
        winner = None
        loser = None

    difference = abs(total1 - total2)

    # --------------------------------------------------------
    # Find resource contributing most to difference
    # --------------------------------------------------------

    pivot = (
        resource_gaps
        .pivot(
            index="resource",
            columns="area",
            values="shortage"
        )
        .fillna(0)
    )

    if area1 not in pivot.columns:
        pivot[area1] = 0

    if area2 not in pivot.columns:
        pivot[area2] = 0

    pivot["difference"] = (
        pivot[area1] - pivot[area2]
    )

    pivot["absolute_difference"] = (
        pivot["difference"].abs()
    )

    pivot = pivot.sort_values(
        "absolute_difference",
        ascending=False
    )

    contribution_rows = []

    for resource, row in pivot.iterrows():

        contribution_rows.append({
            "resource": resource,
            "area1_shortage": float(row[area1]),
            "area2_shortage": float(row[area2]),
            "difference": float(row["difference"]),
            "absolute_difference": float(
                row["absolute_difference"]
            )
        })

    biggest_contributor = (
        contribution_rows[0]
        if contribution_rows
        else None
    )

    return {
        "type": "area_pair",
        "areas": [area1, area2],
        "date_used": str(date_used.date()),
        "totals": {
            area1: total1,
            area2: total2
        },
        "winner": winner,
        "loser": loser,
        "difference": difference,
        "resource_contributions": contribution_rows,
        "biggest_contributor": biggest_contributor,
        "message": (
            f"{winner} has the greater overall resource "
            f"shortage on {date_used.date()}."
            if winner
            else (
                f"{area1} and {area2} have equal overall "
                f"resource shortages on {date_used.date()}."
            )
        )
    }


# ============================================================
# REPORT GENERATOR
# ============================================================

def generate_report(
    gap_result=None,
    trend_result=None,
    comparison_result=None,
    relevant_gap_data=None
):

    report_sections = []

    if (
        relevant_gap_data is not None
        and not relevant_gap_data.empty
    ):

        MAX_DETAIL_ROWS = 50

        relevant = relevant_gap_data.copy()

        relevant["date"] = (
            relevant["date"]
            .apply(normalize_date_value)
        )

        relevant = relevant.sort_values(
            [
                "date",
                "area",
                "resource"
            ],
            na_position="last"
        )

        total_rows = len(relevant)

        if total_rows > MAX_DETAIL_ROWS:
            display_data = relevant.tail(
                MAX_DETAIL_ROWS
            )

            truncation_note = (
                f"\n(Showing the latest "
                f"{MAX_DETAIL_ROWS} of "
                f"{total_rows} matching records.)"
            )
        else:
            display_data = relevant
            truncation_note = ""

        detail_lines = []

        for _, row in display_data.iterrows():

            date_value = row["date"]

            date_text = (
                date_value.strftime("%Y-%m-%d")
                if pd.notna(date_value)
                else "Unknown"
            )

            detail_lines.append(
                f"- {row['area']} | "
                f"{row['resource']} | "
                f"{date_text} | "
                f"needed={row['needed_quantity']} | "
                f"distributed={row['distributed_quantity']} | "
                f"gap={row['gap']} | "
                f"status={row['status']}"
            )

        report_sections.append(
            "RELEVANT GAP DETAILS\n"
            "These records directly match the "
            "user's question:\n"
            + "\n".join(detail_lines)
            + truncation_note
        )

    if gap_result is not None:

        shortages = gap_result[
            gap_result["status"] == "Shortage"
        ]

        surpluses = gap_result[
            gap_result["status"] == "Surplus"
        ]

        okay = gap_result[
            gap_result["status"] == "Okay"
        ]

        report_sections.append(
            "OVERALL GAP ANALYSIS SUMMARY\n"
            f"- Total dataset records with a shortage: "
            f"{len(shortages)}\n"
            f"- Total dataset records with a surplus: "
            f"{len(surpluses)}\n"
            f"- Total dataset records with no gap: "
            f"{len(okay)}"
        )

    if trend_result is not None:

        report_sections.append(
            "TREND FINDING\n"
            f"- {trend_result['message']}"
        )

    if (
        comparison_result is not None
        and comparison_result.get("ranking")
    ):

        comparison_type = (
            comparison_result.get("type")
        )

        if comparison_type == "trend":

            winner = comparison_result.get(
                "winner"
            )

            report_sections.append(
                "TREND COMPARISON\n"
                f"- {comparison_result['message']}"
            )

            if winner:

                report_sections.append(
                    f"- Winner: {winner['area']}\n"
                    f"- First gap: {winner['first_gap']}\n"
                    f"- Last gap: {winner['last_gap']}\n"
                    f"- Change: {winner['change']}"
                )

        elif comparison_type == "worsening_current":

            winner = comparison_result.get(
                "winner"
            )

            report_sections.append(
                "WORSENING SHORTAGE COMPARISON\n"
                f"- {comparison_result['message']}"
            )

            if winner:

                report_sections.append(
                    f"- Area: {winner['area']}\n"
                    f"- First gap: {winner['first_gap']}\n"
                    f"- Current gap: {winner['last_gap']}\n"
                    f"- Increase: {winner['change']}"
                )

        else:

            label_key = (
                "resource"
                if comparison_type == "resource"
                else "area"
            )

            ranking_lines = [
                f"  {i + 1}. "
                f"{row[label_key]} - "
                f"gap {row['gap']} "
                f"({row['status']})"
                for i, row in enumerate(
                    comparison_result["ranking"]
                )
            ]

            report_sections.append(
                "COMPARISON\n"
                f"- {comparison_result['message']}\n"
                + "\n".join(ranking_lines)
            )

    if (
        comparison_result is not None
        and comparison_result.get("type")
        == "area_pair"
    ):

        contributor = (
            comparison_result
            .get("biggest_contributor")
        )

        report_sections.append(
            "AREA PAIR COMPARISON\n"
            f"- {comparison_result['message']}\n"
            f"- Overall shortage totals: "
            f"{comparison_result['totals']}\n"
            f"- Difference: "
            f"{comparison_result['difference']}"
        )

        if contributor:

            report_sections.append(
                "RESOURCE CONTRIBUTION\n"
                f"- Resource: "
                f"{contributor['resource']}\n"
                f"- {comparison_result['areas'][0]} "
                f"shortage: "
                f"{contributor['area1_shortage']}\n"
                f"- {comparison_result['areas'][1]} "
                f"shortage: "
                f"{contributor['area2_shortage']}\n"
                f"- Difference: "
                f"{contributor['difference']}"
            )

    if not report_sections:

        return {
            "report_text": (
                "No analysis results were provided "
                "to generate a report."
            ),
            "sections_included": []
        }

    return {
        "report_text": "\n\n".join(
            report_sections
        ),
        "sections_included": [
            "relevant_gap_details"
            if (
                relevant_gap_data is not None
                and not relevant_gap_data.empty
            )
            else None,

            "gap_analysis"
            if gap_result is not None
            else None,

            "trend"
            if trend_result is not None
            else None,

            "comparison"
            if comparison_result is not None
            else None
        ]
    }