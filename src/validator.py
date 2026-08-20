# ============================================================
# validator.py
# ============================================================
#
# FINAL VALIDATION / RESPONSE LAYER
#
# Architecture:
#
# User Question
#      |
#      v
# Analyst Agent
#      |
#      |-- gap_result
#      |-- trend_result
#      |-- comparison_result
#      |-- draft_answer
#      |
#      v
# Deterministic Validator
#      |
#      v
# Final Grounded Answer
#
# IMPORTANT:
# The validator does NOT blindly trust the analyst's winner.
# Important numerical answers are independently recalculated
# from gap_result.
#
# ============================================================

import math
import pandas as pd

from agent import analyst_agent


# ============================================================
# BASIC HELPERS
# ============================================================

def safe_number(value):
    """
    Convert a value to float safely.
    """

    try:
        if value is None:
            return None

        if isinstance(value, str):
            value = value.strip()

            if not value:
                return None

            value = value.replace(",", "")

        number = float(value)

        if not math.isfinite(number):
            return None

        return number

    except (ValueError, TypeError):
        return None


def format_number(value):
    """
    Human-friendly number formatting.
    """

    number = safe_number(value)

    if number is None:
        return "unknown"

    if number.is_integer():
        return f"{int(number):,}"

    return f"{number:,.2f}"


def normalize_text(value):
    """
    Case-insensitive normalized text.
    """

    if value is None:
        return ""

    return str(value).strip().casefold()


def safe_date(value):
    """
    Convert value to pandas Timestamp safely.
    """

    if value is None:
        return None

    try:
        timestamp = pd.to_datetime(
            value,
            errors="coerce"
        )

        if pd.isna(timestamp):
            return None

        return timestamp

    except Exception:
        return None


def format_date(value):
    """
    Format dates consistently.
    """

    date_value = safe_date(value)

    if date_value is None:
        return "the available reporting period"

    return date_value.strftime("%Y-%m-%d")


# ============================================================
# RESULT NORMALIZATION
# ============================================================

def is_dict(value):
    return isinstance(value, dict)


def is_list(value):
    return isinstance(value, list)


def normalize_result(result):
    """
    Make sure an analysis result is represented as a dict.

    Prevents errors such as:

        AttributeError:
        'str' object has no attribute 'get'
    """

    if result is None:
        return {}

    if isinstance(result, dict):
        return result

    if isinstance(result, str):
        return {
            "message": result
        }

    return {
        "message": str(result)
    }


# ============================================================
# GAP RESULT NORMALIZATION
# ============================================================

def normalize_gap_dataframe(gap_result):
    """
    Normalize gap_result into a DataFrame.

    Handles:
        DataFrame
        list of dictionaries
        dictionary
        None
    """

    if gap_result is None:
        return pd.DataFrame()

    if isinstance(gap_result, pd.DataFrame):

        result = gap_result.copy()

    elif isinstance(gap_result, list):

        try:
            result = pd.DataFrame(
                gap_result
            )

        except Exception:
            return pd.DataFrame()

    elif isinstance(gap_result, dict):

        if "data" in gap_result:

            try:
                result = pd.DataFrame(
                    gap_result["data"]
                )

            except Exception:
                return pd.DataFrame()

        elif "records" in gap_result:

            try:
                result = pd.DataFrame(
                    gap_result["records"]
                )

            except Exception:
                return pd.DataFrame()

        else:

            try:
                result = pd.DataFrame(
                    gap_result
                )

            except Exception:
                return pd.DataFrame()

    else:

        return pd.DataFrame()

    if result.empty:
        return result

    # --------------------------------------------------------
    # Normalize dates
    # --------------------------------------------------------

    if "date" in result.columns:

        result["date"] = pd.to_datetime(
            result["date"],
            errors="coerce"
        )

    # --------------------------------------------------------
    # Normalize numerical columns
    # --------------------------------------------------------

    for column in [
        "needed_quantity",
        "distributed_quantity",
        "gap"
    ]:

        if column in result.columns:

            result[column] = pd.to_numeric(
                result[column],
                errors="coerce"
            )

    return result


# ============================================================
# TREND RESULT HELPERS
# ============================================================

def extract_trend_winner(comparison_result):
    """
    Safely extract a trend winner.
    """

    result = normalize_result(
        comparison_result
    )

    winner = result.get(
        "winner"
    )

    if isinstance(winner, dict):
        return winner

    return None


def build_trend_answer(comparison_result):
    """
    Build final answer for a trend result.
    """

    result = normalize_result(
        comparison_result
    )

    winner = extract_trend_winner(
        result
    )

    if winner is None:
        return None

    area = winner.get(
        "area"
    )

    resource = winner.get(
        "resource"
    )

    first_gap = safe_number(
        winner.get(
            "first_gap"
        )
    )

    last_gap = safe_number(
        winner.get(
            "last_gap"
        )
    )

    change = safe_number(
        winner.get(
            "change"
        )
    )

    first_date = format_date(
        winner.get(
            "first_date"
        )
    )

    last_date = format_date(
        winner.get(
            "last_date"
        )
    )

    if not area:
        return None

    resource_text = (
        str(resource)
        if resource
        else "resource"
    )

    if change is None:

        if (
            first_gap is not None
            and last_gap is not None
        ):

            change = (
                last_gap
                - first_gap
            )

    if (
        first_gap is not None
        and last_gap is not None
        and change is not None
    ):

        return (
            f"{area} has the biggest increase in "
            f"{resource_text.lower()} shortage over time. "
            f"Its gap changed from "
            f"{format_number(first_gap)} units on "
            f"{first_date} to "
            f"{format_number(last_gap)} units on "
            f"{last_date}, an increase of "
            f"{format_number(change)} units."
        )

    return (
        f"{area} has the biggest increase in "
        f"{resource_text.lower()} shortage over time."
    )


# ============================================================
# WORSENING + CURRENT GAP HELPERS
# ============================================================

def build_worsening_current_answer(
    comparison_result
):
    """
    Build final answer for:

    Which area has a worsening medicine shortage
    and currently has the largest medicine gap?
    """

    result = normalize_result(
        comparison_result
    )

    winner = extract_trend_winner(
        result
    )

    if winner is None:
        return None

    area = winner.get(
        "area"
    )

    resource = winner.get(
        "resource"
    )

    first_gap = safe_number(
        winner.get(
            "first_gap"
        )
    )

    last_gap = safe_number(
        winner.get(
            "last_gap"
        )
    )

    change = safe_number(
        winner.get(
            "change"
        )
    )

    if change is None:

        if (
            first_gap is not None
            and last_gap is not None
        ):

            change = (
                last_gap
                - first_gap
            )

    if not area:
        return None

    resource_text = (
        str(resource)
        if resource
        else "resource"
    )

    answer = (
        f"{area} has a worsening "
        f"{resource_text.lower()} shortage and "
        f"currently has the largest gap among "
        f"the areas with worsening shortages."
    )

    if (
        first_gap is not None
        and last_gap is not None
    ):

        answer += (
            f" Its gap increased from "
            f"{format_number(first_gap)} to "
            f"{format_number(last_gap)} units"
        )

        if change is not None:

            answer += (
                f", an increase of "
                f"{format_number(change)} units"
            )

        answer += "."

    else:

        answer += "."

    return answer


# ============================================================
# AREA PAIR COMPARISON
# ============================================================

def extract_pairwise_result(
    comparison_result
):
    """
    Safely normalize pairwise comparison result.
    """

    result = normalize_result(
        comparison_result
    )

    if result.get(
        "type"
    ) != "area_pair":

        return None

    winner = result.get(
        "winner"
    )

    if not isinstance(
        winner,
        str
    ):

        winner = None

    loser = result.get(
        "loser"
    )

    if not isinstance(
        loser,
        str
    ):

        loser = None

    totals = result.get(
        "totals"
    )

    if not isinstance(
        totals,
        dict
    ):

        totals = {}

    contributor = result.get(
        "biggest_contributor"
    )

    if not isinstance(
        contributor,
        dict
    ):

        contributor = None

    areas = result.get(
        "areas"
    )

    if not isinstance(
        areas,
        list
    ):

        areas = []

    return {
        "winner": winner,
        "loser": loser,
        "totals": totals,
        "difference": safe_number(
            result.get(
                "difference"
            )
        ),
        "date_used": result.get(
            "date_used"
        ),
        "biggest_contributor": contributor,
        "areas": areas
    }


def build_pairwise_answer(
    comparison_result
):
    """
    Build final answer for:

    Compare Lahore and Multan.
    Which area has the greater overall resource shortage,
    and which resource contributes most to the difference?
    """

    parsed = extract_pairwise_result(
        comparison_result
    )

    if parsed is None:
        return None

    winner = parsed["winner"]
    loser = parsed["loser"]

    if not winner or not loser:
        return None

    totals = parsed["totals"]

    winner_total = safe_number(
        totals.get(
            winner
        )
    )

    loser_total = safe_number(
        totals.get(
            loser
        )
    )

    difference = parsed[
        "difference"
    ]

    if (
        difference is None
        and winner_total is not None
        and loser_total is not None
    ):

        difference = (
            winner_total
            - loser_total
        )

    date_used = format_date(
        parsed[
            "date_used"
        ]
    )

    # --------------------------------------------------------
    # MAIN COMPARISON
    # --------------------------------------------------------

    if (
        winner_total is not None
        and loser_total is not None
        and difference is not None
    ):

        answer = (
            f"{winner} has the greater overall "
            f"resource shortage than {loser} "
            f"as of {date_used}. "
            f"{winner}'s total shortage is "
            f"{format_number(winner_total)} units, "
            f"compared with "
            f"{format_number(loser_total)} units "
            f"for {loser}, a difference of "
            f"{format_number(abs(difference))} units."
        )

    elif (
        winner_total is not None
        and loser_total is not None
    ):

        answer = (
            f"{winner} has the greater overall "
            f"resource shortage than {loser} "
            f"as of {date_used}. "
            f"{winner}'s total shortage is "
            f"{format_number(winner_total)} units, "
            f"compared with "
            f"{format_number(loser_total)} units "
            f"for {loser}."
        )

    else:

        answer = (
            f"{winner} has the greater overall "
            f"resource shortage than {loser}."
        )

    # --------------------------------------------------------
    # BIGGEST CONTRIBUTOR
    # --------------------------------------------------------

    contributor = parsed[
        "biggest_contributor"
    ]

    if not contributor:
        return answer

    resource = contributor.get(
        "resource"
    )

    if not resource:
        return answer

    area1_shortage = safe_number(
        contributor.get(
            "area1_shortage"
        )
    )

    area2_shortage = safe_number(
        contributor.get(
            "area2_shortage"
        )
    )

    absolute_difference = safe_number(
        contributor.get(
            "absolute_difference"
        )
    )

    areas = parsed.get(
        "areas",
        []
    )

    area1 = (
        areas[0]
        if len(areas) >= 1
        else None
    )

    area2 = (
        areas[1]
        if len(areas) >= 2
        else None
    )

    # --------------------------------------------------------
    # Match contributor values to winner / loser
    # --------------------------------------------------------

    if (
        area1 == winner
        and area2 == loser
    ):

        winner_resource_shortage = (
            area1_shortage
        )

        loser_resource_shortage = (
            area2_shortage
        )

    elif (
        area2 == winner
        and area1 == loser
    ):

        winner_resource_shortage = (
            area2_shortage
        )

        loser_resource_shortage = (
            area1_shortage
        )

    else:

        winner_resource_shortage = (
            area1_shortage
        )

        loser_resource_shortage = (
            area2_shortage
        )

    # --------------------------------------------------------
    # Contributor with both values
    # --------------------------------------------------------

    if (
        winner_resource_shortage is not None
        and loser_resource_shortage is not None
    ):

        answer += (
            f" {resource} contributes the most "
            f"to this difference: {winner} has "
            f"{format_number(winner_resource_shortage)} "
            f"units of {resource} shortage "
            f"versus "
            f"{format_number(loser_resource_shortage)} "
            f"units in {loser}"
        )

        if absolute_difference is not None:

            answer += (
                f", a difference of "
                f"{format_number(absolute_difference)} "
                f"units."
            )

        else:

            answer += "."

    else:

        answer += (
            f" {resource} is the resource "
            f"contributing most to the "
            f"difference."
        )

    return answer


# ============================================================
# NORMAL AREA / RESOURCE COMPARISON
# ============================================================

def extract_normal_comparison_winner(
    comparison_result
):
    """
    Normalize normal area/resource comparison.
    """

    result = normalize_result(
        comparison_result
    )

    winner = result.get(
        "winner"
    )

    if not isinstance(
        winner,
        dict
    ):

        return None

    return winner


def build_normal_comparison_answer(comparison_result):
    """
    Build answer for normal area/resource comparisons.

    Metric-aware: preserves whether the user asked for "gap"
    (generic), "shortage", or "surplus" - never silently renames
    a requested "gap" into "shortage" just because the winning row
    happens to be positive.
    """

    result = normalize_result(comparison_result)

    if result.get("no_match"):

        metric = result.get("metric", "gap")
        comparison_type = result.get("type", "area")

        if comparison_type == "resource":

            context = result.get("area", "the requested area")

            return f"No {metric} records were found for any resource in {context}."

        resource = result.get("resource", "the requested resource")

        return f"No {metric} records were found for any area for {str(resource).lower()}."

    winner = extract_normal_comparison_winner(result)

    if winner is None:
        return None

    comparison_type = result.get("type", "area")
    direction = result.get("direction", "largest")
    metric = result.get("metric", "gap")

    area = winner.get("area")
    resource = winner.get("resource") or result.get("resource")
    gap = safe_number(winner.get("gap"))
    status = winner.get("status")
    date_used = format_date(result.get("date_used"))

    direction_text = "smallest" if direction == "smallest" else "largest"

    metric_label = metric if metric in ("shortage", "surplus") else "gap"

    value_text = (
        format_number(gap) if metric_label == "gap"
        else format_number(abs(gap))
    )

    if comparison_type == "resource":

        area_name = result.get("area") or area

        if metric_label == "gap":

            return (
                f"The resource with the {direction_text} gap in "
                f"{area_name} is {resource}, with a gap of "
                f"{value_text} units ({status}) as of {date_used}."
            )

        return (
            f"The resource with the {direction_text} {metric_label} in "
            f"{area_name} is {resource}, with a {metric_label} of "
            f"{value_text} units as of {date_used}."
        )

    if metric_label == "gap":

        return (
            f"The area with the {direction_text} gap for "
            f"{str(resource).lower()} is {area}, with a gap of "
            f"{value_text} units ({status}) as of {date_used}."
        )

    return (
        f"The area with the {direction_text} {str(resource).lower()} "
        f"{metric_label} is {area}, with a {metric_label} of "
        f"{value_text} units as of {date_used}."
    )


# ============================================================
# SINGLE RECORD
# ============================================================

def build_single_record_answer(
    relevant_gap_data
):
    """
    Build answer when exactly one allocation record exists.
    """

    data = normalize_gap_dataframe(
        relevant_gap_data
    )

    if data.empty:
        return None

    if len(data) != 1:
        return None

    row = data.iloc[0]

    area = row.get(
        "area"
    )

    resource = row.get(
        "resource"
    )

    needed = safe_number(
        row.get(
            "needed_quantity"
        )
    )

    distributed = safe_number(
        row.get(
            "distributed_quantity"
        )
    )

    gap = safe_number(
        row.get(
            "gap"
        )
    )

    status = row.get(
        "status"
    )

    date_value = format_date(
        row.get(
            "date"
        )
    )

    if gap is None:

        if (
            needed is not None
            and distributed is not None
        ):

            gap = (
                needed
                - distributed
            )

    resource_text = (
        str(resource).lower()
        if resource is not None
        else "resource"
    )

    if status == "Shortage":

        return (
            f"{area} had a "
            f"{resource_text} shortage "
            f"of {format_number(abs(gap))} units "
            f"in {date_value}. "
            f"{format_number(needed)} units were "
            f"needed and "
            f"{format_number(distributed)} units "
            f"were distributed."
        )

    if status == "Surplus":

        return (
            f"{area} had a "
            f"{resource_text} surplus "
            f"of {format_number(abs(gap))} units "
            f"in {date_value}. "
            f"{format_number(needed)} units were "
            f"needed and "
            f"{format_number(distributed)} units "
            f"were distributed."
        )

    return (
        f"{area} had no allocation gap for "
        f"{resource_text} in "
        f"{date_value}."
    )


# ============================================================
# VALIDATE GLOBAL TREND
# ============================================================

def validate_trend_result(
    comparison_result,
    gap_result,
    resource=None,
    direction="largest"
):
    """
    Independently determine the area with the biggest change
    (increase or decrease, per `direction`) in shortage over time.

    The analyst's proposed winner is NOT trusted.
    The validator recalculates the result from gap_result.
    """

    data = normalize_gap_dataframe(gap_result)

    if data.empty:
        return None

    required = {"area", "resource", "gap", "date"}

    if not required.issubset(set(data.columns)):
        return None

    if resource:

        data = data[
            data["resource"].map(normalize_text) == normalize_text(resource)
        ]

    data = data.dropna(subset=["area", "resource", "gap", "date"])

    if data.empty:
        return None

    data["gap"] = pd.to_numeric(data["gap"], errors="coerce")
    data = data.dropna(subset=["gap"])

    if data.empty:
        return None

    candidates = []

    for area, group in data.groupby("area"):

        group = group.sort_values("date")

        if len(group) < 2:
            continue

        first = group.iloc[0]
        last = group.iloc[-1]

        first_gap = safe_number(first["gap"])
        last_gap = safe_number(last["gap"])

        if first_gap is None or last_gap is None:
            continue

        change = last_gap - first_gap

        candidates.append({
            "area": area,
            "resource": resource if resource else first["resource"],
            "first_gap": first_gap,
            "last_gap": last_gap,
            "change": change,
            "first_date": first["date"],
            "last_date": last["date"]
        })

    if not candidates:
        return None

    if direction == "smallest":

        # Biggest DECREASE = most negative change
        winner = min(candidates, key=lambda item: item["change"])

        if winner["change"] >= 0:
            return None

    else:

        # Biggest INCREASE = most positive change
        winner = max(candidates, key=lambda item: item["change"])

        if winner["change"] <= 0:
            return None

    return winner

# ============================================================
# VALIDATE PAIRWISE RESULT
# ============================================================

def validate_pairwise_result(
    comparison_result,
    gap_result
):
    """
    Independently recompute area-pair comparison.

    Only positive gaps count as shortage.

    Negative gaps are surplus and therefore contribute 0
    to overall shortage.
    """

    result = normalize_result(
        comparison_result
    )

    if result.get(
        "type"
    ) != "area_pair":

        return None

    areas = result.get(
        "areas"
    )

    # --------------------------------------------------------
    # Try explicit areas first
    # --------------------------------------------------------

    if not isinstance(
        areas,
        list
    ) or len(areas) < 2:

        winner_from_result = result.get(
            "winner"
        )

        loser_from_result = result.get(
            "loser"
        )

        if (
            isinstance(
                winner_from_result,
                str
            )
            and
            isinstance(
                loser_from_result,
                str
            )
        ):

            areas = [
                winner_from_result,
                loser_from_result
            ]

        else:

            return None

    area1 = areas[0]
    area2 = areas[1]

    if not isinstance(
        area1,
        str
    ) or not isinstance(
        area2,
        str
    ):

        return None

    data = normalize_gap_dataframe(
        gap_result
    )

    if data.empty:
        return None

    required = {
        "area",
        "resource",
        "gap",
        "date"
    }

    if not required.issubset(
        set(data.columns)
    ):

        return None

    data = data.dropna(
        subset=["date"]
    )

    if data.empty:
        return None

    # --------------------------------------------------------
    # Latest reporting date
    # --------------------------------------------------------

    latest_date = data["date"].max()

    latest = data[
        data["date"] == latest_date
    ].copy()

    if latest.empty:
        return None

    # --------------------------------------------------------
    # Only selected areas
    # --------------------------------------------------------

    latest = latest[
        latest["area"].map(
            normalize_text
        ).isin(
            {
                normalize_text(area1),
                normalize_text(area2)
            }
        )
    ].copy()

    if latest.empty:
        return None

    latest["gap"] = pd.to_numeric(
        latest["gap"],
        errors="coerce"
    )

    latest = latest.dropna(
        subset=["gap"]
    )

    if latest.empty:
        return None

    # --------------------------------------------------------
    # Positive gap = shortage
    # Negative gap = surplus
    # Therefore shortage contribution:
    #
    # max(gap, 0)
    # --------------------------------------------------------

    latest["shortage"] = latest[
        "gap"
    ].clip(
        lower=0
    )

    # --------------------------------------------------------
    # Total shortage per area
    # --------------------------------------------------------

    totals = (
        latest
        .groupby("area")["shortage"]
        .sum()
        .to_dict()
    )

    # --------------------------------------------------------
    # Resolve actual area names
    # --------------------------------------------------------

    actual_area1 = None
    actual_area2 = None

    for actual in latest["area"].dropna().unique():

        if normalize_text(actual) == normalize_text(area1):

            actual_area1 = actual

        if normalize_text(actual) == normalize_text(area2):

            actual_area2 = actual

    if (
        actual_area1 is None
        or actual_area2 is None
    ):

        return None

    total1 = safe_number(
        totals.get(
            actual_area1,
            0
        )
    )

    total2 = safe_number(
        totals.get(
            actual_area2,
            0
        )
    )

    if total1 is None:
        total1 = 0

    if total2 is None:
        total2 = 0

    # --------------------------------------------------------
    # Determine winner
    # --------------------------------------------------------

    if total1 >= total2:

        winner = actual_area1
        loser = actual_area2

        winner_total = total1
        loser_total = total2

    else:

        winner = actual_area2
        loser = actual_area1

        winner_total = total2
        loser_total = total1

    overall_difference = (
        winner_total
        - loser_total
    )

    # --------------------------------------------------------
    # Resource-level contribution
    # --------------------------------------------------------

    pivot = (
        latest
        .groupby(
            [
                "area",
                "resource"
            ]
        )["shortage"]
        .sum()
        .reset_index()
    )

    resource_names = sorted(
        pivot[
            "resource"
        ]
        .dropna()
        .unique()
        .tolist()
    )

    contributor = None

    best_difference = -1

    for resource_name in resource_names:

        row1 = pivot[
            (
                pivot["area"]
                == actual_area1
            )
            &
            (
                pivot["resource"]
                == resource_name
            )
        ]

        row2 = pivot[
            (
                pivot["area"]
                == actual_area2
            )
            &
            (
                pivot["resource"]
                == resource_name
            )
        ]

        if row1.empty:

            shortage1 = 0

        else:

            shortage1 = safe_number(
                row1.iloc[0]["shortage"]
            )

        if row2.empty:

            shortage2 = 0

        else:

            shortage2 = safe_number(
                row2.iloc[0]["shortage"]
            )

        if shortage1 is None:
            shortage1 = 0

        if shortage2 is None:
            shortage2 = 0

        resource_difference = abs(
            shortage1
            - shortage2
        )

        if resource_difference > best_difference:

            best_difference = (
                resource_difference
            )

            contributor = {
                "resource": resource_name,
                "area1_shortage": shortage1,
                "area2_shortage": shortage2,
                "absolute_difference":
                    resource_difference
            }

    return {
        "type": "area_pair",
        "areas": [
            actual_area1,
            actual_area2
        ],
        "winner": winner,
        "loser": loser,
        "totals": {
            actual_area1: total1,
            actual_area2: total2
        },
        "difference": overall_difference,
        "date_used": latest_date,
        "biggest_contributor": contributor
    }


# ============================================================
# VALIDATE WORSENING + CURRENT GAP
# ============================================================

def validate_worsening_current_result(
    comparison_result,
    gap_result,
    resource=None
):
    """
    Recalculate:

        1. worsening shortage over time
        2. largest CURRENT gap among worsening areas
    """

    data = normalize_gap_dataframe(
        gap_result
    )

    if data.empty:
        return None

    required = {
        "area",
        "resource",
        "gap",
        "date"
    }

    if not required.issubset(
        set(data.columns)
    ):

        return None

    # --------------------------------------------------------
    # Filter requested resource
    # --------------------------------------------------------

    if resource:

        data = data[
            data["resource"].map(
                normalize_text
            )
            ==
            normalize_text(
                resource
            )
        ]

    data = data.dropna(
        subset=[
            "area",
            "resource",
            "gap",
            "date"
        ]
    )

    if data.empty:
        return None

    data["gap"] = pd.to_numeric(
        data["gap"],
        errors="coerce"
    )

    data = data.dropna(
        subset=["gap"]
    )

    if data.empty:
        return None

    candidates = []

    # --------------------------------------------------------
    # Check every area independently
    # --------------------------------------------------------

    for area, group in data.groupby(
        "area"
    ):

        group = group.sort_values(
            "date"
        )

        if len(group) < 2:
            continue

        first = group.iloc[0]
        last = group.iloc[-1]

        first_gap = safe_number(
            first["gap"]
        )

        last_gap = safe_number(
            last["gap"]
        )

        if (
            first_gap is None
            or last_gap is None
        ):

            continue

        change = (
            last_gap
            - first_gap
        )

        # Positive change = worsening shortage
        if change > 0:

            candidates.append({
                "area": area,
                "resource": (
                    resource
                    if resource
                    else last["resource"]
                ),
                "first_gap": first_gap,
                "last_gap": last_gap,
                "change": change,
                "first_date": first["date"],
                "last_date": last["date"]
            })

    if not candidates:
        return None

    # --------------------------------------------------------
    # Among worsening areas, choose largest CURRENT gap
    # --------------------------------------------------------

    winner = max(
        candidates,
        key=lambda item: item["last_gap"]
    )

    return winner


# ============================================================
# FINAL RESPONSE BUILDER
# ============================================================

def build_final_response(
    question,
    analyst_result
):
    """
    Main final-answer builder.

    Important numerical answers are validated from raw data.
    """

    analyst_result = normalize_result(
        analyst_result
    )

    if analyst_result.get(
        "error"
    ):

        return (
            analyst_result.get(
                "message",
                "The analyst agent failed."
            )
        )

    intent = normalize_result(
        analyst_result.get(
            "intent"
        )
    )

    comparison_result = normalize_result(
        analyst_result.get(
            "comparison_result"
        )
    )

    trend_result = normalize_result(
        analyst_result.get(
            "trend_result"
        )
    )

    gap_result = analyst_result.get(
        "gap_result"
    )

    relevant_gap_data = analyst_result.get(
        "relevant_gap_data"
    )

    comparison_type = intent.get(
        "comparison_type",
        "none"
    )

    resource = intent.get(
        "resource"
    )

    # ========================================================
    # 1. GLOBAL TREND
    # ========================================================

    if comparison_type == "trend":

        trend_direction = comparison_result.get("direction", "largest")
        change_word = "decrease" if trend_direction == "smallest" else "increase"

        validated = validate_trend_result(
            comparison_result,
            gap_result,
            resource=resource,
            direction=trend_direction
        )

        if validated:

            resource_name = str(validated["resource"]).lower()

            article = "a" if change_word == "decrease" else "an"

            return (
                f"{validated['area']} has the biggest "
                f"{change_word} in {resource_name} shortage "
                f"over time. Its gap changed from "
                f"{format_number(validated['first_gap'])} "
                f"units on "
                f"{format_date(validated['first_date'])} "
                f"to "
                f"{format_number(validated['last_gap'])} "
                f"units on "
                f"{format_date(validated['last_date'])}, "
                f"{article} {change_word} of "
                f"{format_number(abs(validated['change']))} "
                f"units."
            )

        # Fallback only if validator cannot calculate
        answer = build_trend_answer(comparison_result)

        if answer:
            return answer
    # ========================================================
    # 2. WORSENING + CURRENT GAP
    # ========================================================

    if comparison_type == "worsening_current":

        validated = (
            validate_worsening_current_result(
                comparison_result,
                gap_result,
                resource=resource
            )
        )

        if validated:

            resource_name = str(
                validated["resource"]
            ).lower()

            return (
                f"{validated['area']} has a worsening "
                f"{resource_name} shortage and currently "
                f"has the largest gap among the areas "
                f"with worsening shortages. "
                f"Its gap increased from "
                f"{format_number(validated['first_gap'])} "
                f"to "
                f"{format_number(validated['last_gap'])} "
                f"units, an increase of "
                f"{format_number(validated['change'])} "
                f"units."
            )

        answer = (
            build_worsening_current_answer(
                comparison_result
            )
        )

        if answer:
            return answer

    # ========================================================
    # 3. AREA PAIR
    # ========================================================

    if comparison_type == "area_pair":

        validated = validate_pairwise_result(
            comparison_result,
            gap_result
        )

        if validated:

            answer = build_pairwise_answer(
                validated
            )

            if answer:
                return answer

        # ----------------------------------------------------
        # Reconstruct directly from intent areas
        # ----------------------------------------------------

        areas = intent.get(
            "areas",
            []
        )

        if (
            isinstance(areas, list)
            and len(areas) >= 2
        ):

            reconstructed = (
                validate_pairwise_result(
                    {
                        "type": "area_pair",
                        "areas": areas
                    },
                    gap_result
                )
            )

            if reconstructed:

                return build_pairwise_answer(
                    reconstructed
                )

    # ========================================================
    # 4. NORMAL AREA / RESOURCE COMPARISON
    # ========================================================

    if (
        intent.get(
            "needs_comparison"
        )
        and comparison_type in {
            "area",
            "resource"
        }
    ):

        answer = (
            build_normal_comparison_answer(
                comparison_result
            )
        )

        if answer:
            return answer

    # ========================================================
    # 5. SINGLE TREND
    # ========================================================

    if (
        intent.get(
            "needs_trend"
        )
        and comparison_type not in {
            "trend",
            "worsening_current"
        }
    ):

        message = trend_result.get(
            "message"
        )

        if message:
            return message

        trend_winner = extract_trend_winner(
            trend_result
        )

        if trend_winner:

            area = trend_winner.get(
                "area"
            )

            resource_name = (
                trend_winner.get(
                    "resource",
                    resource
                )
            )

            change = safe_number(
                trend_winner.get(
                    "change"
                )
            )

            if area:

                if change is not None:

                    return (
                        f"{area} has a "
                        f"{str(resource_name).lower()} "
                        f"shortage trend with a change "
                        f"of {format_number(change)} "
                        f"units over the available period."
                    )

                return (
                    f"{area} has the identified "
                    f"{str(resource_name).lower()} "
                    f"shortage trend."
                )

    # ========================================================
    # 6. SINGLE RECORD
    # ========================================================

    single_answer = (
        build_single_record_answer(
            relevant_gap_data
        )
    )

    if single_answer:
        return single_answer

    # ========================================================
    # 7. ANALYST DRAFT - LAST RESORT
    # ========================================================

    draft = analyst_result.get(
        "draft_answer"
    )

    if (
        isinstance(
            draft,
            str
        )
        and draft.strip()
    ):

        return draft.strip()

    # ========================================================
    # 8. NO MATCH
    # ========================================================

    data = normalize_gap_dataframe(
        relevant_gap_data
    )

    if data.empty:

        return (
            "No matching allocation data was "
            "found for the requested question."
        )

    return (
        f"{len(data)} matching allocation records "
        f"were found, but a specific analytical "
        f"answer could not be constructed."
    )


# ============================================================
# VALIDATION AGENT
# ============================================================

def validation_agent(
    question,
    needs_file,
    distribution_file=None,
    feedback=None
):
    """
    Public entry point used by test_newdataset.py.

    The analyst performs analytical work.

    The validator independently verifies important
    numerical results before returning the final answer.
    """

    try:

        analyst_result = analyst_agent(
            question=question,
            needs_file=needs_file,
            distribution_file=distribution_file,
            feedback=feedback
        )

    except Exception as exc:

        return {
            "success": False,
            "error": True,
            "attempts": 1,
            "message": (
                f"Analyst Agent failed: "
                f"{type(exc).__name__}: {exc}"
            ),
            "final_answer": None
        }

    if not isinstance(
        analyst_result,
        dict
    ):

        return {
            "success": False,
            "error": True,
            "attempts": 1,
            "message": (
                "Analyst agent returned an "
                "invalid result."
            ),
            "final_answer": None
        }

    if analyst_result.get(
        "error"
    ):

        return {
            "success": False,
            "error": True,
            "attempts": 1,
            "message": analyst_result.get(
                "message",
                "Analyst Agent failed."
            ),
            "final_answer": None
        }

    # ========================================================
    # BUILD VERIFIED FINAL ANSWER
    # ========================================================

    try:

        final_answer = build_final_response(
            question=question,
            analyst_result=analyst_result
        )

    except Exception as exc:

        return {
            "success": False,
            "error": True,
            "attempts": 1,
            "message": (
                f"Validation Agent failed while "
                f"building the final answer: "
                f"{type(exc).__name__}: {exc}"
            ),
            "final_answer": None
        }

    if not final_answer:

        final_answer = (
            "No verified answer could be generated "
            "from the available allocation data."
        )

    # ========================================================
    # RETURN
    # ========================================================

    return {
        "success": True,
        "error": False,
        "attempts": 1,
        "message": (
            "Validation completed successfully."
        ),
        "question": question,
        "final_answer": final_answer,

        # Debugging / testing information
        "analyst_result": analyst_result,

        "intent": analyst_result.get(
            "intent"
        ),

        "gap_result": analyst_result.get(
            "gap_result"
        ),

        "relevant_gap_data":
            analyst_result.get(
                "relevant_gap_data"
            ),

        "trend_result":
            analyst_result.get(
                "trend_result"
            ),

        "comparison_result":
            analyst_result.get(
                "comparison_result"
            ),

        "report_text":
            analyst_result.get(
                "report_text"
            )
    }


# ============================================================
# OPTIONAL DIRECT TEST
# ============================================================

if __name__ == "__main__":

    TEST_FILE = (
        "data/ngo_complex_multi_source.csv"
    )

    questions = [

        "Which area has the biggest increase "
        "in food shortage over time?",

        "Which area has a worsening medicine "
        "shortage and currently has the largest "
        "medicine gap?",

        "Compare Lahore and Multan. Which area "
        "has the greater overall resource shortage, "
        "and which resource contributes the most "
        "to the difference?"
    ]

    for question in questions:

        print(
            "\n"
            + "=" * 70
        )

        print(
            "QUESTION:",
            question
        )

        print(
            "=" * 70
        )

        result = validation_agent(
            question=question,
            needs_file=TEST_FILE,
            distribution_file=None
        )

        print(
            "\nSuccess:",
            result["success"]
        )

        print(
            "Attempts:",
            result["attempts"]
        )

        print(
            "\nFinal Answer:\n",
            result["final_answer"]
        )