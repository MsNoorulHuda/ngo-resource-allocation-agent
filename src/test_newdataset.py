# ============================================================
# test_newdataset.py
# ============================================================

from validator import validation_agent


def run_test(label, question, file_path):
    print(f"\n{'=' * 60}")
    print(f"DATASET: {label}")
    print(f"QUESTION: {question}")
    print("=" * 60)

    result = validation_agent(
        question=question,
        needs_file=file_path,
        distribution_file=None
    )

    print("Success:", result["success"])
    print("Attempts:", result["attempts"])

    if result["success"]:
        print("\nFinal Answer:\n", result["final_answer"])
    else:
        print("\nMessage:", result["message"])


if __name__ == "__main__":

   
   run_test(
    "ngo_allocation_large.csv (clean benchmark, 1728 rows)",
    "Which area has the smallest food gap?",
    "data/ngo_allocation_large.csv"
)

   run_test(
    "ngo_allocation_large.csv (clean benchmark, 1728 rows)",
    "Which area has the largest medicine shortage?",
    "data/ngo_allocation_large.csv"
)

   run_test(
    "ngo_messy_dataset.csv (messy naming, 3046 rows)",
    "Which area has the largest clothing shortage?",
    "data/ngo_messy_dataset.csv"
)