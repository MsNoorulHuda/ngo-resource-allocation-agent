# ============================================================
# agent.py
# ============================================================

import json
import re
import pandas as pd

from tools import (
    llm,
    clean_and_map_schema,
    llm_map_unmapped_columns,
    gap_analysis_from_data,
    gap_analysis_from_combined,
    trend_detection,
    trend_comparison,
    worsening_current_gap_comparison,
    area_comparison,
    resource_comparison,
    pairwise_area_comparison,
    generate_report
)


REQUIRED_NEEDS_COLUMNS = {
    "area", "resource", "needed_quantity", "date"
}

REQUIRED_DISTRIBUTION_COLUMNS = {
    "area", "resource", "distributed_quantity", "date"
}


def resolve_schema(file_path):

    result = clean_and_map_schema(file_path)

    if result["unmapped_columns"]:

        llm_result = llm_map_unmapped_columns(
            result["cleaned_data"],
            result["unmapped_columns"],
            result["column_mapping"]
        )

        rename_map = {
            column: info["suggested_as"]
            for column, info in llm_result["auto_mapped"].items()
        }

        if rename_map:

            result["cleaned_data"] = (
                result["cleaned_data"].rename(columns=rename_map)
            )

            result["column_mapping"].update(rename_map)

        result["unmapped_columns"] = [
            column for column in result["unmapped_columns"]
            if column not in rename_map
        ]

        result["needs_user_confirmation"] = (
            llm_result["needs_user_confirmation"]
        )

    else:

        result["needs_user_confirmation"] = []

    return result


def normalize_requested_period(year, month):

    if year is None and month is None:
        return None

    try:
        year = int(year) if year is not None else None
    except (ValueError, TypeError):
        year = None

    try:
        month = int(month) if month is not None else None
    except (ValueError, TypeError):
        month = None

    if month is not None and not 1 <= month <= 12:
        month = None

    if year is not None and not 1900 <= year <= 2100:
        year = None

    if year is None and month is not None:
        month = None

    if year is None and month is None:
        return None

    return {"year": year, "month": month}


def normalize_dates(data):

    result = data.copy()

    result["date"] = pd.to_datetime(result["date"], errors="coerce")

    return result


def filter_by_period(data, period):

    if period is None:
        return data.copy()

    filtered = normalize_dates(data)

    filtered = filtered.dropna(subset=["date"])

    if period.get("year") is not None:

        filtered = filtered[filtered["date"].dt.year == period["year"]]

    if period.get("month") is not None:

        filtered = filtered[filtered["date"].dt.month == period["month"]]

    return filtered


def normalize_text(value):

    if value is None:
        return ""

    return str(value).strip().casefold()


def resolve_entity(value, available_values):

    if value is None:
        return None

    normalized = normalize_text(value)

    for actual_value in available_values:

        if normalize_text(actual_value) == normalized:
            return actual_value

    return None


def detect_trend_direction(question_normalized):

    decrease_phrases = [
        "decrease", "decreasing", "decreased",
        "reduction", "reduce", "reducing",
        "improve", "improving", "improvement",
        "getting better", "better",
        "decline", "declining", "declined",
        "drop", "dropping", "dropped",
        "fall", "falling", "fallen",
        "shrink", "shrinking", "shrunk"
    ]

    increase_phrases = [
        "increase", "increasing", "increased",
        "worsening", "worse", "getting worse", "worst"
    ]

    has_decrease = any(p in question_normalized for p in decrease_phrases)
    has_increase = any(p in question_normalized for p in increase_phrases)

    if has_decrease and not has_increase:
        return "smallest"

    return "largest"


def detect_comparison_metric(question_normalized):

    surplus_keywords = [
        "surplus", "excess", "oversupply", "over-supply",
        "overstock", "surfeit"
    ]

    shortage_keywords = [
        "shortage", "deficit", "shortfall", "lack", "scarcity"
    ]

    if any(k in question_normalized for k in surplus_keywords):
        return "surplus"

    if any(k in question_normalized for k in shortage_keywords):
        return "shortage"

    return "gap"


def detect_comparison_direction(question_normalized):

    smallest_keywords = ["smallest", "lowest", "least", "minimum", "best"]

    if any(k in question_normalized for k in smallest_keywords):
        return "smallest"

    return "largest"


def select_ranking_winner(ranking, metric, direction):
    """
    Selects the correct winner from a ranking list, respecting BOTH
    the requested metric (shortage-only, surplus-only, or raw gap)
    and the requested direction (largest or smallest magnitude).

    IMPORTANT: if the requested metric has no matching candidates
    (e.g. "largest surplus" but no area has a surplus), this
    returns None. Callers MUST check for None and produce a
    "no matching records" response - never silently fall back to
    the full ranking, since that could return a shortage when a
    surplus was specifically requested.
    """

    if not ranking:
        return None

    if metric == "shortage":
        candidates = [row for row in ranking if row["gap"] > 0]
    elif metric == "surplus":
        candidates = [row for row in ranking if row["gap"] < 0]
    else:
        candidates = ranking

    if not candidates:
        return None

    if metric == "surplus":
        key_func = lambda row: -row["gap"]
    else:
        key_func = lambda row: row["gap"]

    if direction == "smallest":
        return min(candidates, key=key_func)

    return max(candidates, key=key_func)


def understand_question(question, available_areas, available_resources):

    prompt = f"""
You are the intent detection component of an NGO
resource allocation analysis system.

Available areas:
{available_areas}

Available resources:
{available_resources}

User question:
"{question}"

Determine:

area:
- One specific area if exactly one area is requested.
- Otherwise null.

areas:
- List of explicitly mentioned areas.
- Return [] if fewer than two areas are mentioned.

resource:
- One specific resource if explicitly mentioned.
- Otherwise null.

year:
- Four digit year only if explicitly mentioned.
- Otherwise null.

month:
- Month number only if explicitly mentioned.
- Otherwise null.

needs_trend:
true when the question asks about:
- trend
- increase/decrease
- change over time
- worsening/improving
- getting worse/better

needs_comparison:
true when the question asks:
- largest
- smallest
- highest
- lowest
- greatest
- least
- which area
- which resource
- compare

comparison_type:
Choose ONE:
- "none"
- "area"
- "resource"
- "trend"
- "area_pair"
- "worsening_current"

Rules:

1. "Which area has the largest food shortage?"
   -> comparison_type = "area"

2. "Which resource has the largest shortage in Multan?"
   -> comparison_type = "resource"

3. "Which area has the biggest increase in food shortage over time?"
   -> comparison_type = "trend"

3b. "Which area has the biggest decrease in food shortage over time?"
   -> comparison_type = "trend"

4. "Which area has a worsening medicine shortage
   and currently has the largest medicine gap?"
   -> comparison_type = "worsening_current"

5. "Compare Lahore and Multan. Which area has
   the greater overall resource shortage?"
   -> comparison_type = "area_pair"
   -> areas = ["Lahore", "Multan"]

6. Never invent entities.

comparison_metric:
Only relevant when needs_comparison is true and comparison_type is
"area" or "resource".

Return "shortage" if the question explicitly says shortage, deficit,
shortfall, lack, or scarcity.

Return "surplus" if the question explicitly says surplus, excess,
oversupply, overstock, or surfeit.

Return "gap" if the question just says "gap" generically, without
the words shortage or surplus (gap can be positive or negative).

comparison_direction:
Only relevant when needs_comparison is true and comparison_type is
"area" or "resource".

Return "largest" if the question asks for the biggest, highest,
greatest, worst, or most severe value.

Return "smallest" if the question asks for the smallest, lowest,
least, minimum, or best value.

Default to "largest" if unclear.

trend_direction:
Only relevant when needs_trend is true OR comparison_type is "trend"
or "worsening_current".

Return "increase" for worsening/getting worse/increasing/growing/
rising shortage, or biggest/largest increase. This is also the
default for a plain "trend" or "change over time" question.

Return "decrease" for improving/getting better/decreasing shortage,
decline, drop, fall, reduction, shrinking, or biggest/largest
decrease/improvement.

Return null if the question is not about trend/direction at all.

Return ONLY valid JSON:

{{
    "area": null,
    "areas": [],
    "resource": null,
    "year": null,
    "month": null,
    "needs_trend": false,
    "needs_comparison": false,
    "comparison_type": "none",
    "comparison_metric": null,
    "comparison_direction": null,
    "trend_direction": null
}}
"""

    response = llm.invoke(prompt).content.strip()

    if response.startswith("```"):

        lines = response.splitlines()

        lines = [
            line for line in lines
            if not line.strip().startswith("```")
        ]

        response = "\n".join(lines)

    try:

        parsed = json.loads(response)

    except json.JSONDecodeError:

        parsed = {
            "area": None, "areas": [], "resource": None,
            "year": None, "month": None,
            "needs_trend": False, "needs_comparison": False,
            "comparison_type": "none", "comparison_metric": None,
            "comparison_direction": None, "trend_direction": None
        }

    return parsed


def format_number(value):

    try:

        number = float(value)

        if number.is_integer():
            return str(int(number))

        return str(number)

    except (ValueError, TypeError):

        return str(value)


def build_grounded_draft(
    question, intent, relevant_gap_data,
    trend_result=None, comparison_result=None
):

    # --------------------------------------------------------
    # AREA PAIR
    # --------------------------------------------------------

    if (
        comparison_result
        and comparison_result.get("type") == "area_pair"
        and comparison_result.get("winner")
    ):

        areas = comparison_result["areas"]
        totals = comparison_result["totals"]
        winner = comparison_result["winner"]
        loser = comparison_result["loser"]
        difference = comparison_result["difference"]
        contributor = comparison_result.get("biggest_contributor")

        answer = (
            f"{winner} has the greater overall resource shortage than "
            f"{loser} as of {comparison_result['date_used']}. "
            f"{winner}'s total shortage is {format_number(totals[winner])} "
            f"units, compared with {format_number(totals[loser])} units "
            f"for {loser}, a difference of {format_number(difference)} units."
        )

        if contributor:

            resource = contributor["resource"]

            winner_resource_shortage = (
                contributor["area1_shortage"] if areas[0] == winner
                else contributor["area2_shortage"]
            )

            loser_resource_shortage = (
                contributor["area2_shortage"] if areas[0] == winner
                else contributor["area1_shortage"]
            )

            resource_difference = contributor["absolute_difference"]

            answer += (
                f" {resource} contributes the most to this difference: "
                f"{winner} has {format_number(winner_resource_shortage)} "
                f"units of {resource} shortage versus "
                f"{format_number(loser_resource_shortage)} units in "
                f"{loser}, a difference of "
                f"{format_number(resource_difference)} units."
            )

        return answer

    # --------------------------------------------------------
    # GLOBAL TREND COMPARISON
    # --------------------------------------------------------

    if (
        comparison_result
        and comparison_result.get("type") == "trend"
        and comparison_result.get("winner")
    ):

        winner = comparison_result["winner"]
        direction = comparison_result.get("direction", "largest")
        change_word = "decrease" if direction == "smallest" else "increase"
        article = "a" if change_word == "decrease" else "an"

        return (
            f"{winner['area']} has the biggest {change_word} in "
            f"{winner['resource']} shortage over time. "
            f"Its gap changed from {format_number(winner['first_gap'])} "
            f"on {winner['first_date'].strftime('%Y-%m-%d')} to "
            f"{format_number(winner['last_gap'])} on "
            f"{winner['last_date'].strftime('%Y-%m-%d')}, {article} "
            f"{change_word} of {format_number(abs(winner['change']))} units."
        )

    # --------------------------------------------------------
    # WORSENING + CURRENT GAP
    # --------------------------------------------------------

    if (
        comparison_result
        and comparison_result.get("type") == "worsening_current"
        and comparison_result.get("winner")
    ):

        winner = comparison_result["winner"]

        return (
            f"{winner['area']} has a worsening {winner['resource']} "
            f"shortage and currently has the largest gap among the "
            f"areas with worsening shortages. Its gap increased from "
            f"{format_number(winner['first_gap'])} to "
            f"{format_number(winner['last_gap'])} units, an increase "
            f"of {format_number(winner['change'])} units."
        )

    # --------------------------------------------------------
    # NORMAL AREA / RESOURCE COMPARISON - NO MATCH
    # (fixes: "largest surplus" silently returning a shortage)
    # --------------------------------------------------------

    if (
        intent.get("needs_comparison")
        and comparison_result
        and comparison_result.get("no_match")
    ):

        metric = comparison_result.get("metric", "gap")
        comparison_type = comparison_result.get("type", "area")

        if comparison_type == "resource":

            context = comparison_result.get("area", "the requested area")

            return (
                f"No {metric} records were found for any resource "
                f"in {context}."
            )

        resource_name = comparison_result.get("resource", "the requested resource")

        return (
            f"No {metric} records were found for any area for "
            f"{str(resource_name).lower()}."
        )

    # --------------------------------------------------------
    # NORMAL AREA / RESOURCE COMPARISON
    # (fixes: "smallest gap" being labeled "smallest shortage")
    # --------------------------------------------------------

    if (
        intent.get("needs_comparison")
        and comparison_result
        and comparison_result.get("winner")
    ):

        winner = comparison_result["winner"]
        comparison_type = comparison_result.get("type", "area")
        metric = comparison_result.get("metric", "gap")

        direction_word = (
            "smallest" if comparison_result.get("direction") == "smallest"
            else "largest"
        )

        gap = winner["gap"]
        status = winner["status"]
        date_used = comparison_result["date_used"]

        # If the user asked generically for "gap", always call it a
        # gap (never silently rename it to shortage/surplus based on
        # sign). If they asked specifically for shortage/surplus, use
        # that exact word.
        metric_label = metric if metric in ("shortage", "surplus") else "gap"

        value_text = (
            format_number(gap) if metric_label == "gap"
            else format_number(abs(gap))
        )

        if comparison_type == "resource":

            resource_name = winner["resource"]
            area_name = comparison_result["area"]

            if metric_label == "gap":

                return (
                    f"The resource with the {direction_word} gap in "
                    f"{area_name} is {resource_name}, with a gap of "
                    f"{value_text} units ({status}) as of {date_used}."
                )

            return (
                f"The resource with the {direction_word} {metric_label} in "
                f"{area_name} is {resource_name}, with a {metric_label} of "
                f"{value_text} units as of {date_used}."
            )

        area_name = winner["area"]
        resource_name = comparison_result.get("resource", "")

        if metric_label == "gap":

            return (
                f"The area with the {direction_word} gap for "
                f"{str(resource_name).lower()} is {area_name}, with a "
                f"gap of {value_text} units ({status}) as of {date_used}."
            )

        return (
            f"The area with the {direction_word} "
            f"{str(resource_name).lower()} {metric_label} is {area_name}, "
            f"with a {metric_label} of {value_text} units as of "
            f"{date_used}."
        )

    # --------------------------------------------------------
    # SINGLE TREND
    # --------------------------------------------------------

    if intent.get("needs_trend") and trend_result is not None:

        return trend_result.get(
            "message", "No trend information is available."
        )

    # --------------------------------------------------------
    # NO MATCHING DATA
    # --------------------------------------------------------

    if relevant_gap_data is None or relevant_gap_data.empty:

        return "No matching allocation data was found for the requested question."

    # --------------------------------------------------------
    # SINGLE RECORD
    # --------------------------------------------------------

    rows = normalize_dates(relevant_gap_data)

    if len(rows) == 1:

        row = rows.iloc[0]

        area = row["area"]
        resource = row["resource"]
        date_value = row["date"]

        date_text = (
            "the available reporting period" if pd.isna(date_value)
            else date_value.strftime("%B %Y")
        )

        needed = format_number(row["needed_quantity"])
        distributed = format_number(row["distributed_quantity"])
        gap = float(row["gap"])
        gap_abs = format_number(abs(gap))
        status = row["status"]

        if status == "Shortage":

            return (
                f"{area} had a {str(resource).lower()} shortage of "
                f"{gap_abs} units in {date_text}. {needed} units were "
                f"needed and {distributed} units were distributed."
            )

        if status == "Surplus":

            return (
                f"{area} had a {str(resource).lower()} surplus of "
                f"{gap_abs} units in {date_text}. {needed} units were "
                f"needed and {distributed} units were distributed."
            )

        return (
            f"{area} had no allocation gap for {str(resource).lower()} "
            f"in {date_text}."
        )

    # --------------------------------------------------------
    # AREA + RESOURCE
    # --------------------------------------------------------

    if intent.get("area") and intent.get("resource"):

        latest_row = rows.sort_values("date").iloc[-1]

        area = latest_row["area"]
        resource = latest_row["resource"]
        date_value = latest_row["date"]

        needed = format_number(latest_row["needed_quantity"])
        distributed = format_number(latest_row["distributed_quantity"])
        gap = float(latest_row["gap"])

        if gap > 0:

            return (
                f"The latest available record for {area}'s "
                f"{str(resource).lower()} allocation shows a shortage "
                f"of {format_number(abs(gap))} units in "
                f"{date_value.strftime('%B %Y')}. {needed} units were "
                f"needed and {distributed} units were distributed."
            )

        if gap < 0:

            return (
                f"The latest available record for {area}'s "
                f"{str(resource).lower()} allocation shows a surplus "
                f"of {format_number(abs(gap))} units."
            )

        return (
            f"The latest available record for {area}'s "
            f"{str(resource).lower()} allocation shows no gap."
        )

    # --------------------------------------------------------
    # FALLBACK
    # --------------------------------------------------------

    return (
        f"{len(rows)} matching allocation records were found, but the "
        f"question requires a more specific analytical interpretation."
    )


def analyst_agent(question, needs_file, distribution_file=None, feedback=None):

    needs_clean = resolve_schema(needs_file)
    needs_df = needs_clean["cleaned_data"]
    needs_columns = set(needs_df.columns)

    is_combined = (
        distribution_file is None
        and "needed_quantity" in needs_columns
        and "distributed_quantity" in needs_columns
    )

    if is_combined:

        required_combined = REQUIRED_NEEDS_COLUMNS | {"distributed_quantity"}
        missing_columns = required_combined - needs_columns

        if missing_columns:

            return {
                "question": question, "error": True,
                "message": (
                    f"Cannot run analysis. Missing required columns: "
                    f"{sorted(missing_columns)}."
                )
            }

        gap_result = gap_analysis_from_combined(needs_df)

    else:

        if distribution_file is None:

            return {
                "question": question, "error": True,
                "message": (
                    "A separate distribution file is required because "
                    "the supplied dataset does not contain "
                    "distributed_quantity."
                )
            }

        distribution_clean = resolve_schema(distribution_file)
        distribution_df = distribution_clean["cleaned_data"]
        distribution_columns = set(distribution_df.columns)

        missing_needs = REQUIRED_NEEDS_COLUMNS - needs_columns
        missing_distribution = REQUIRED_DISTRIBUTION_COLUMNS - distribution_columns

        if missing_needs or missing_distribution:

            return {
                "question": question, "error": True,
                "message": (
                    f"Cannot run analysis.\nMissing from needs file: "
                    f"{sorted(missing_needs)}.\nMissing from distribution "
                    f"file: {sorted(missing_distribution)}."
                )
            }

        gap_result = gap_analysis_from_data(needs_df, distribution_df)

    gap_result = normalize_dates(gap_result)

    available_areas = sorted(gap_result["area"].dropna().unique().tolist())
    available_resources = sorted(gap_result["resource"].dropna().unique().tolist())

    intent = understand_question(question, available_areas, available_resources)

    intent["area"] = resolve_entity(intent.get("area"), available_areas)
    intent["resource"] = resolve_entity(intent.get("resource"), available_resources)

    detected_areas = []

    question_normalized = normalize_text(question)

    for actual_area in available_areas:

        area_normalized = normalize_text(actual_area)

        pattern = (
            r"(?<!\w)"
            + r"\s+".join(re.escape(part) for part in area_normalized.split())
            + r"(?!\w)"
        )

        if re.search(pattern, question_normalized):

            detected_areas.append(actual_area)

    intent["areas"] = detected_areas

    if len(detected_areas) == 1 and not intent.get("area"):

        intent["area"] = detected_areas[0]

    detected_resources = []

    for actual_resource in available_resources:

        resource_normalized = normalize_text(actual_resource)

        pattern = (
            r"(?<!\w)"
            + r"\s+".join(re.escape(part) for part in resource_normalized.split())
            + r"(?!\w)"
        )

        if re.search(pattern, question_normalized):

            detected_resources.append(actual_resource)

    if len(detected_resources) == 1 and not intent.get("resource"):

        intent["resource"] = detected_resources[0]

    period = normalize_requested_period(intent.get("year"), intent.get("month"))

    intent["year"] = period["year"] if period else None
    intent["month"] = period["month"] if period else None
    intent["needs_trend"] = bool(intent.get("needs_trend"))
    intent["needs_comparison"] = bool(intent.get("needs_comparison"))

    q = question_normalized

    pairwise_phrases = ["compare", "compared", "versus", "vs", "difference between"]

    if len(detected_areas) >= 2 and any(phrase in q for phrase in pairwise_phrases):

        intent["comparison_type"] = "area_pair"
        intent["needs_comparison"] = True

    trend_phrases = [
        "over time", "increase", "increased", "increasing",
        "change over", "worsening", "worse", "getting worse",
        "improving", "improve", "decrease", "decreasing", "decreased",
        "decline", "declining", "declined", "drop", "dropping",
        "fall", "falling", "shrink", "shrinking"
    ]

    if intent.get("resource") and any(phrase in q for phrase in trend_phrases):

        if (
            ("currently" in q or "current" in q)
            and ("largest" in q or "biggest" in q or "greatest" in q)
        ):

            intent["comparison_type"] = "worsening_current"

        elif not intent.get("area"):

            intent["comparison_type"] = "trend"

        else:

            intent["needs_trend"] = True

    relevant_gap_data = gap_result.copy()

    if intent.get("area"):

        relevant_gap_data = relevant_gap_data[
            relevant_gap_data["area"] == intent["area"]
        ]

    if intent.get("resource"):

        relevant_gap_data = relevant_gap_data[
            relevant_gap_data["resource"] == intent["resource"]
        ]

    if period:

        relevant_gap_data = filter_by_period(relevant_gap_data, period)

    trend_result = None

    if intent.get("needs_trend") and intent.get("area") and intent.get("resource"):

        trend_data = gap_result[
            (gap_result["area"] == intent["area"])
            & (gap_result["resource"] == intent["resource"])
        ].copy()

        if period:

            trend_data = filter_by_period(trend_data, period)

        trend_result = trend_detection(
            trend_data, area=intent["area"], resource=intent["resource"]
        )

    comparison_result = None

    if intent.get("comparison_type") == "area_pair" and len(detected_areas) >= 2:

        area1 = detected_areas[0]
        area2 = detected_areas[1]

        comparison_data = gap_result.copy()

        if period:

            comparison_data = filter_by_period(comparison_data, period)

        comparison_result = pairwise_area_comparison(comparison_data, area1, area2)
        comparison_result["type"] = "area_pair"

    elif intent.get("comparison_type") == "trend" and intent.get("resource"):

        comparison_data = gap_result.copy()

        if period:

            comparison_data = filter_by_period(comparison_data, period)

        llm_direction = intent.get("trend_direction")

        if llm_direction == "decrease":
            trend_direction = "smallest"
        elif llm_direction == "increase":
            trend_direction = "largest"
        else:
            trend_direction = detect_trend_direction(q)

        comparison_result = trend_comparison(
            comparison_data,
            resource=intent["resource"],
            direction=trend_direction
        )

        comparison_result["type"] = "trend"
        comparison_result["direction"] = trend_direction
        comparison_result["ranking"] = comparison_result.get("ranking", [])

    elif intent.get("comparison_type") == "worsening_current" and intent.get("resource"):

        comparison_data = gap_result.copy()

        if period:

            comparison_data = filter_by_period(comparison_data, period)

        comparison_result = worsening_current_gap_comparison(
            comparison_data, resource=intent["resource"]
        )

        comparison_result["type"] = "worsening_current"
        comparison_result["ranking"] = comparison_result.get("ranking", [])

    elif intent.get("needs_comparison") and intent.get("area") and not intent.get("resource"):

        comparison_data = gap_result.copy()

        if period:

            comparison_data = filter_by_period(comparison_data, period)

        comparison_date = None

        normalized = normalize_dates(comparison_data)
        normalized = normalized.dropna(subset=["date"])

        if not normalized.empty:

            comparison_date = normalized["date"].max()

        comparison_result = resource_comparison(
            comparison_data if period else gap_result,
            area=intent["area"],
            date=comparison_date
        )

        comparison_result["type"] = "resource"

        ranking = comparison_result.get("ranking", [])

        if ranking:

            metric = intent.get("comparison_metric") or detect_comparison_metric(q)
            direction = intent.get("comparison_direction") or detect_comparison_direction(q)

            winner = select_ranking_winner(ranking, metric, direction)

            comparison_result["metric"] = metric
            comparison_result["direction"] = direction
            comparison_result["winner"] = winner

            if winner is None:
                comparison_result["no_match"] = True

    elif intent.get("needs_comparison") and intent.get("resource") and not intent.get("area"):

        comparison_data = gap_result.copy()

        if period:

            comparison_data = filter_by_period(comparison_data, period)

        comparison_date = None

        normalized = normalize_dates(comparison_data)
        normalized = normalized.dropna(subset=["date"])

        if not normalized.empty:

            comparison_date = normalized["date"].max()

        comparison_result = area_comparison(
            comparison_data if period else gap_result,
            resource=intent["resource"],
            date=comparison_date
        )

        comparison_result["type"] = "area"

        ranking = comparison_result.get("ranking", [])

        if ranking:

            metric = intent.get("comparison_metric") or detect_comparison_metric(q)
            direction = intent.get("comparison_direction") or detect_comparison_direction(q)

            winner = select_ranking_winner(ranking, metric, direction)

            comparison_result["metric"] = metric
            comparison_result["direction"] = direction
            comparison_result["winner"] = winner

            if winner is None:
                comparison_result["no_match"] = True

    report = generate_report(
        gap_result=gap_result,
        trend_result=trend_result,
        comparison_result=comparison_result,
        relevant_gap_data=relevant_gap_data
    )

    draft_answer = build_grounded_draft(
        question=question,
        intent=intent,
        relevant_gap_data=relevant_gap_data,
        trend_result=trend_result,
        comparison_result=comparison_result
    )

    return {
        "question": question,
        "error": False,
        "intent": intent,
        "draft_answer": draft_answer,
        "gap_result": gap_result,
        "relevant_gap_data": relevant_gap_data,
        "trend_result": trend_result,
        "comparison_result": comparison_result,
        "report_text": report["report_text"]
    }


if __name__ == "__main__":

    result = analyst_agent(
        question="Which resource has the smallest gap in Lahore?",
        needs_file="data/ngo_complex_multi_source.csv"
    )

    if result["error"]:

        print("ERROR:", result["message"])

    else:

        print("Question:", result["question"])
        print("\nDetected intent:", result["intent"])
        print("\nDraft answer:\n", result["draft_answer"])