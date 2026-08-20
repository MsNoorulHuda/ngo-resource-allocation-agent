# NGO Resource Allocation Analytics Agent

An agentic AI system that analyzes NGO donation, distribution, and needs data to identify resource gaps, trends, and allocation imbalances, and provides evidence-backed recommendations to NGO staff.

## Why This Exists

NGOs collect donations and distribute resources across communities, but donation, distribution, and needs data is often scattered across separate spreadsheets or manual records maintained by different teams. This makes it difficult and time-consuming to identify resource shortages, over-allocation, and changing demand patterns.

Existing tools either focus on donor management rather than resource-gap analysis (e.g. CiviCRM), or are feature-rich but too costly and complex for smaller NGOs to adopt (e.g. Salesforce Nonprofit Cloud). See [PROBLEM.md](PROBLEM.md) for the full research behind this project.

## The Solution

This system accepts NGO resource data (in varying formats), cleans and standardizes it, and lets staff ask natural-language questions about it — gaps, trends, and comparisons — receiving evidence-based answers grounded entirely in the underlying data.

**Example:**
> **Question:** Which area has the largest medicine shortage?
>
> **Answer:** The area with the largest medicine shortage is Lahore, with a shortage of 360 units as of 2026-12-01.

## Features

- **Flexible schema mapping** — automatically adapts to different NGO dataset column-naming conventions, using rule-based matching first and an LLM fallback for unrecognized columns (never guessing silently — low-confidence mappings are flagged for review)
- **Natural-language question answering** — ask about shortages, surpluses, trends, and comparisons in plain English
- **Multi-step reasoning** — the Analyst Agent dynamically decides which analytical tools a question needs and chains them together (e.g. a "why" question triggers gap analysis + trend detection + area comparison)
- **Deterministic calculations** — all numbers are computed by Python, never by the LLM, eliminating a major source of hallucination
- **Independent validation** — a second agent verifies that every number and claim in the final answer is actually supported by the underlying data before it's shown to the user
- **Supports both single-file and two-file datasets** — works whether needs/distribution data comes combined in one file or split across two

## Architecture

The system uses a two-agent design:

```
User Question
      |
      v
Analyst Agent  --------> Schema Mapping --> Gap Analysis --> Trend/Comparison Tools
      |
      v
Structured Report + Draft Answer
      |
      v
Validation & Recommendation Agent
      |
      v
Final Evidence-Based Answer
```

- **Analyst Agent** interprets the question, selects and runs the relevant tools, and builds a grounded draft answer.
- **Validation & Recommendation Agent** independently checks the draft against the actual calculated data before releasing the final answer.

Full details, including tool specifications and failure handling, are in [ARCHITECTURE.md](ARCHITECTURE.md).

## Installation

```bash
git clone <your-repo-url>
cd ngo-resource-allocation-agent
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux

pip install -r requirements.txt
```

Create a `.env` file in the project root with your Groq API key:
```
GROQ_API_KEY=your_key_here
```

## Usage

### Command line

```python
from src.validator import validation_agent

result = validation_agent(
    question="Which area has the largest food shortage?",
    needs_file="data/ngo_allocation_large.csv"
)

print(result["final_answer"])
```

### Web interface

```bash
streamlit run src/app.py
```

This opens a browser interface where you can select a dataset and ask questions directly.

## Project Structure

```
ngo-resource-allocation-agent/
├── README.md
├── PROBLEM.md
├── ARCHITECTURE.md
├── TESTING.md
├── requirements.txt
├── data/                  # Sample datasets
├── src/
│   ├── tools.py           # 5 analytical tools
│   ├── agent.py            # Analyst Agent
│   ├── validator.py        # Validation & Recommendation Agent
│   └── app.py               # Streamlit frontend
```

## Roadmap

- Fuzzy matching for area names to handle minor spelling/casing inconsistencies within a single dataset (e.g. "Gujranwala" vs "Gujranwla")
- Support for additional custom metadata fields (e.g. program category, donor type) as filters for more granular analysis
- Conversation memory across multiple related questions

## License

See [LICENSE](LICENSE).
