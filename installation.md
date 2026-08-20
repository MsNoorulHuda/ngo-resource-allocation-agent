INSTALLATION.md

# Installation Guide

## Prerequisites

- Python 3.10+
- pip
- Groq API Key

## Installation

1. Clone or download the project.

2. Open the project folder:

```bash
cd ngo-resource-allocation-agent

3. Create a virtual environment:

python -m venv venv

4. Activate the virtual environment.
Windows

venv\Scripts\activate

5. Install dependencies:
pip install -r requirements.txt

6. Create a .env file in the project root and add:
GROQ_API_KEY=your_api_key_here

7. Run the project:
python src/test_newdataset.py

The system should now execute the test questions and display the validated answers.

