# Architecture

## Overview

This project uses two agents instead of one. The first agent analyzes the data and figures out an answer. The second agent checks that answer against the real numbers before it is shown to the user. This helps avoid the AI making up information that the data doesn't actually support.

No CrewAI is used here. Both agents are built manually using LangChain and Groq. The actual calculations (like shortage numbers) are done by normal Python functions, not by the AI. The AI is only used for understanding the question, deciding what to check, and explaining the results in plain language.

## Overall System Diagram

```
USER
  ↓
┌─────────────────┐
│ AGENT 1          │
│ Orchestrator +   │
│ Analysis         │
└────────┬─────────┘
         ↓
    CUSTOM TOOLS
┌────────┼─────────┐
↓        ↓         ↓
Gap    Trend    Comparison
Analysis Detection  etc.
         ↓
┌─────────────────┐
│ AGENT 2          │
│ Validation +      │
│ Recommendation    │
└────────┬─────────┘
         ↓
    FINAL ANSWER
```

## Agent 1: Analyst Agent

This agent handles the investigation part.

What it does:
- Reads the user's question
- Decides which tool(s) it needs to answer it
- Calls the tools (sometimes more than one, depending on the question)
- Looks at the results and decides if it needs to check anything else
- Writes a draft answer based on what the tools returned

What it does not do:
- It does not calculate anything itself. All numbers come from tools.
- It does not give the final answer to the user directly.

## Agent 2: Validation Agent

This agent checks the Analyst Agent's work.

What it does:
- Compares the draft answer with the actual tool outputs
- If something in the draft is not backed by the data, it sends feedback to the Analyst Agent to re-check the analysis. This retry is limited to a maximum of three retry attempts to prevent the agents from getting stuck in a loop.
- If everything checks out, it writes the final answer with the reasoning and a recommendation

What it does not do:
- It does not call the analysis tools itself
- It does not make the final allocation decision. That stays with the NGO staff.

## How a simple question flows

Example: "Which area has the highest food shortage?"

```
User asks question
  ↓
Analyst Agent calls Gap Analysis Tool
  ↓
Analyst Agent writes draft answer
  ↓
Validation Agent checks the number
  ↓
Final answer shown to user
```

## How a harder question flows

Example: "Why has Area B's medicine shortage gone up?"

```
User asks question
  ↓
Analyst Agent calls Gap Analysis Tool (confirms there is a shortage)
  ↓
Analyst Agent calls Trend Detection Tool (checks if it's getting worse)
  ↓
Analyst Agent calls Area Comparison Tool (checks if other areas have the same issue)
  ↓
Analyst Agent combines all this into a draft answer
  ↓
Validation Agent checks all the numbers
  ↓
Final answer shown to user, with the reasoning behind it
```

The Analyst Agent decides on its own how many tools it needs to call. It's not a fixed step-by-step process every time. Simple questions use fewer tools, harder ones use more.

## Tools

These are the tools the Analyst Agent can use. All of them are regular Python functions, not AI.

- **Data Cleaning Tool**: takes in raw NGO data (in varying formats), performs basic cleaning such as handling missing values, duplicates, and invalid entries, and includes a schema mapping step that identifies which columns represent area/location, resource type, needed quantity, distributed quantity, and date, even if the column names differ across datasets (e.g. "District" or "Commodity" instead of standard names). Flags any columns it cannot confidently map for user review.
- **Gap Analysis Tool**: takes in needs data and distribution data, gives back the gap (needed minus distributed), labeled as shortage, surplus, or okay
- **Trend Detection Tool**: takes in data over time, gives back whether the situation is getting better, worse, or staying the same
- **Area Comparison Tool**: takes in gap results from multiple areas, gives back a ranking of which areas are worst off
- **Report Generator Tool**: takes validated analytical results and formats them into a structured summary containing key findings, supporting metrics, and recommendations.

## State

The system only keeps track of information during one question at a time. So while answering a question, the Analyst Agent remembers what earlier tools in that same question returned, so it can decide the next step.

It does not remember previous questions the user asked before. So if someone asks a follow-up like "compare that to last month," the system won't understand "that" refers to the earlier answer. This kind of memory is not part of this version of the project. It's listed as a future improvement in ROADMAP.md.

The state also stores the tool results and intermediate findings produced during the current investigation so the Analyst Agent can use them when deciding what to do next.

## What happens when something goes wrong

- **Data has missing or bad values**: Cleaning tool flags it, and the agent tells the user instead of guessing
- **No data found for an area/resource**: Agent says so clearly instead of making something up
- **Draft answer doesn't match the actual numbers**: Validation Agent sends feedback to the Analyst Agent to re-check the analysis. The system allows a maximum of three retry attempts before returning a failure message.
- **Validation still fails after three retry attempts**: System tells the user it couldn't get a reliable answer instead of looping indefinitely.
- **Question is unclear**: Agent asks the user to clarify instead of assuming

## Tech stack (not fully locked yet)

- LLM: Groq's Llama 3.1 (already used in earlier bootcamp labs)
- Framework: LangChain, with a custom agent setup (no CrewAI)
- Data: Python with pandas

These may change slightly once actual coding starts.
