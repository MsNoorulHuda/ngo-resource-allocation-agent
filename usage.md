USAGE.md

How to Use
1. Place the NGO dataset inside the data/ folder
2. Activate the virtual environment.
3. Run the test/application file.
4. Enter an NGO resource-related question in natural language.
5. The Analyst Agent analyzes the data and selects the required analysis.
6. The Validator Agent verifies the result against the dataset.
7. The system returns a grounded final answer.
Run
python src/test_newdataset.py

Example Questions
Which resource has the biggest shortage in Multan?

Which area has the biggest increase in food shortage over time?

Compare Lahore and Multan. Which area has the greater overall resource shortage?

The system supports gap analysis, trend analysis, comparisons, and shortage detection using the provided NGO allocation data.
