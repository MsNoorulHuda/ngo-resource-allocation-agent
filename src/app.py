# ============================================================
# app.py
# Simple Streamlit frontend for the NGO Resource Allocation Agent
# ============================================================

import streamlit as st
from validator import validation_agent

st.set_page_config(page_title="NGO Resource Allocation Agent", page_icon="📊")

st.title("📊 NGO Resource Allocation Analytics Agent")
st.write(
    "Ask a question about resource allocation, gaps, trends, or "
    "comparisons across areas and resources."
)

# ------------------------------------------------------------
# Dataset selection
# ------------------------------------------------------------

DATASETS = {
    "Standard dataset (Lahore, Multan, Faisalabad, Sialkot)": {
        "needs_file": "data/needs.csv",
        "distribution_file": "data/distribution.csv"
    },
    "Large allocation dataset (12 areas, 1729 rows)": {
        "needs_file": "data/ngo_allocation_large.csv",
        "distribution_file": None
    },
    "Messy dataset (inconsistent naming, 3046 rows)": {
        "needs_file": "data/ngo_messy_dataset.csv",
        "distribution_file": None
    },
    "Complex multi-source dataset (fully renamed columns, 10000 rows)": {
        "needs_file": "data/ngo_complex_multi_source.csv",
        "distribution_file": None
    }
}

dataset_label = st.selectbox("Choose a dataset", list(DATASETS.keys()))
selected = DATASETS[dataset_label]

# ------------------------------------------------------------
# Question input
# ------------------------------------------------------------

question = st.text_input(
    "Your question",
    placeholder="e.g. Which area has the largest food shortage?"
)

ask_clicked = st.button("Ask", type="primary")

# ------------------------------------------------------------
# Run the agent and show the result
# ------------------------------------------------------------

if ask_clicked:

    if not question.strip():
        st.warning("Please enter a question first.")

    else:

        with st.spinner("Analyzing..."):

            result = validation_agent(
                question=question,
                needs_file=selected["needs_file"],
                distribution_file=selected["distribution_file"]
            )

        st.markdown("---")

        if result.get("success"):

            st.markdown("### Answer")
            st.markdown(result["final_answer"])

            with st.expander("Show details (intent detected, attempts)"):
                st.json(result.get("intent", {}))
                st.write("Attempts:", result.get("attempts", 1))

        else:

            st.error(result.get("message", "The agent could not produce an answer."))