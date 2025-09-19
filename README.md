# OpenISave
OpenISave is a web app designed to help you track your expenses, manage budgets, and convert between multiple currencies — all without the need for a paid subscription. Inspired by popular budgeting tools like Cookie, this app brings most of their functionality to an open-source, accessible platform.

**Key Features:**

- Add, edit, and delete income and expense transactions  
- Multi-currency support: USD, CNY, EUR, GBP, JPY, and more  
- Free and open-source — no premium features  
- Runs locally on your own computer using Python  
- Generates charts and PDF reports with Matplotlib and Pandas  

## Project Structure
openisave
├---finance_app.py
├---requirements.txt
├---templates
       ├---index.html
       ├---server.py

## Requirements

- Python 3.7 or higher  

### Install dependencies

```bash
# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

