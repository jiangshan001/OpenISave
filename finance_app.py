# app.py - Enhanced Personal Finance Web App
from flask import Flask, render_template, request, jsonify, send_file
import sqlite3
import json
from datetime import datetime, date
import os
import requests
import threading
import io
import matplotlib
matplotlib.use('Agg')  # Non-GUI backend
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import pandas as pd

app = Flask(__name__)

# Configuration
DB_FILE = "finance_web.db"
CURRENCIES = ["CNY", "USD", "EUR", "GBP", "JPY", "CAD", "AUD"]
EXPENSE_CATS = ["Food", "Transport", "Rent", "Utilities", "Entertainment", "Groceries", "Health", "Clothing", "Education", "Other"]
INCOME_CATS = ["Salary", "Bonus", "Part-time", "Interest", "Gift", "Investment", "Freelance", "Other"]
ALLOWED_TYPES = {"income", "expense", "transfer"}

# --- Database helpers ---
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS accounts 
                     (id INTEGER PRIMARY KEY, name TEXT, currency TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS transactions 
                     (id INTEGER PRIMARY KEY, date TEXT, type TEXT, category TEXT, 
                      amount REAL, currency TEXT, account_id INTEGER, note TEXT,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS exchange_rates 
                     (id INTEGER PRIMARY KEY, from_currency TEXT, to_currency TEXT, 
                      rate REAL, date TEXT, source TEXT DEFAULT 'manual')''')
        
        # Indexes
        c.execute('CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(type)')
        
        # Default account
        c.execute("SELECT COUNT(*) FROM accounts")
        if c.fetchone()[0] == 0:
            c.execute("INSERT INTO accounts (name, currency) VALUES (?, ?)", ("Main Account", "CNY"))
        
        # Default exchange rates
        c.execute("SELECT COUNT(*) FROM exchange_rates")
        if c.fetchone()[0] == 0:
            default_rates = [
                ("USD", "CNY", 7.2), ("EUR", "CNY", 7.8), ("GBP", "CNY", 9.0),
                ("CNY", "USD", 1/7.2), ("USD", "EUR", 0.92), ("EUR", "USD", 1/0.92)
            ]
            today = date.today().isoformat()
            for from_curr, to_curr, rate in default_rates:
                c.execute("INSERT INTO exchange_rates (from_currency, to_currency, rate, date, source) VALUES (?, ?, ?, ?, ?)",
                         (from_curr, to_curr, rate, today, "default"))
        conn.commit()

def get_db_conn():
    conn = sqlite3.connect(DB_FILE, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    conn.row_factory = sqlite3.Row
    return conn

# --- Utility functions ---
def parse_iso_date(datestr):
    """Expect YYYY-MM-DD; raise ValueError if invalid."""
    try:
        return datetime.strptime(datestr, "%Y-%m-%d").date()
    except Exception as e:
        raise ValueError("Date must be in YYYY-MM-DD format")

def get_accounts():
    with get_db_conn() as conn:
        rows = conn.execute('SELECT * FROM accounts ORDER BY name').fetchall()
        return [dict(r) for r in rows]

def get_transactions(limit=100, account_id=None, year=None, month=None):
    with get_db_conn() as conn:
        query = '''SELECT t.*, a.name as account_name 
                   FROM transactions t 
                   LEFT JOIN accounts a ON t.account_id = a.id'''
        params = []
        conditions = []
        if account_id:
            conditions.append('t.account_id = ?')
            params.append(account_id)
        if year and month:
            # Ensure month two-digit
            conditions.append("strftime('%Y', t.date) = ? AND strftime('%m', t.date) = ?")
            params.extend([str(year), f"{int(month):02d}"])
        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)
        query += ' ORDER BY t.date DESC, t.id DESC LIMIT ?'
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

def get_exchange_rates(limit=50):
    with get_db_conn() as conn:
        rows = conn.execute('''SELECT * FROM exchange_rates 
                               ORDER BY date DESC LIMIT ?''', (limit,)).fetchall()
        return [dict(r) for r in rows]

def get_latest_rate(from_currency, to_currency):
    """Return latest rate from->to. If missing try reverse, then via USD if possible, else 1.0"""
    if from_currency == to_currency:
        return 1.0
    with get_db_conn() as conn:
        r = conn.execute('''SELECT rate FROM exchange_rates 
                            WHERE from_currency = ? AND to_currency = ? 
                            ORDER BY date DESC LIMIT 1''', (from_currency, to_currency)).fetchone()
        if r:
            return r['rate']
        # Try reverse
        r2 = conn.execute('''SELECT rate FROM exchange_rates 
                             WHERE from_currency = ? AND to_currency = ? 
                             ORDER BY date DESC LIMIT 1''', (to_currency, from_currency)).fetchone()
        if r2 and r2['rate'] != 0:
            return 1.0 / r2['rate']
        # Try via USD if available
        if from_currency != 'USD' and to_currency != 'USD':
            r_from_usd = conn.execute('''SELECT rate FROM exchange_rates WHERE from_currency = ? AND to_currency = ? ORDER BY date DESC LIMIT 1''', (from_currency, 'USD')).fetchone()
            r_usd_to = conn.execute('''SELECT rate FROM exchange_rates WHERE from_currency = ? AND to_currency = ? ORDER BY date DESC LIMIT 1''', ('USD', to_currency)).fetchone()
            if r_from_usd and r_usd_to and r_from_usd['rate'] and r_usd_to['rate']:
                return r_from_usd['rate'] * r_usd_to['rate']
    return 1.0

# --- API Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/accounts', methods=['GET'])
def api_get_accounts():
    return jsonify(get_accounts())

@app.route('/api/accounts', methods=['POST'])
def api_add_account():
    data = request.json or {}
    name = (data.get('name') or '').strip()
    currency = (data.get('currency') or 'CNY').upper()
    if not name:
        return jsonify({'error': 'Account name is required'}), 400
    if currency not in CURRENCIES:
        return jsonify({'error': f'Unsupported currency: {currency}'}), 400
    with get_db_conn() as conn:
        cur = conn.execute('INSERT INTO accounts (name, currency) VALUES (?, ?)', (name, currency))
        account_id = cur.lastrowid
        conn.commit()
    return jsonify({'id': account_id, 'name': name, 'currency': currency})

@app.route('/api/transactions', methods=['GET'])
def api_get_transactions():
    limit = request.args.get('limit', 100, type=int)
    account_id = request.args.get('account_id', type=int)
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    transactions = get_transactions(limit=limit, account_id=account_id, year=year, month=month)
    return jsonify(transactions)

@app.route('/api/transactions', methods=['POST'])
def api_add_transaction():
    data = request.json or {}
    # Validation
    required_fields = ['date', 'type', 'category', 'amount', 'currency']
    for fld in required_fields:
        if fld not in data:
            return jsonify({'error': f'{fld} is required'}), 400
    # date
    try:
        d = parse_iso_date(data['date'])
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    tx_type = data['type'].lower().strip()
    if tx_type not in ALLOWED_TYPES:
        return jsonify({'error': f'invalid type (allowed: {sorted(ALLOWED_TYPES)})'}), 400
    category = data['category']
    # basic category check (optional)
    if tx_type == 'expense' and category not in EXPENSE_CATS:
        # allow custom but warn
        pass
    if tx_type == 'income' and category not in INCOME_CATS:
        pass
    try:
        amount = float(data['amount'])
        if amount <= 0:
            raise ValueError()
    except:
        return jsonify({'error': 'Invalid amount; must be positive number'}), 400
    currency = (data['currency'] or 'CNY').upper()
    if currency not in CURRENCIES:
        return jsonify({'error': f'Unsupported currency: {currency}'}), 400
    account_id = data.get('account_id')
    if not account_id:
        with get_db_conn() as conn:
            first_account = conn.execute('SELECT id FROM accounts LIMIT 1').fetchone()
            if first_account:
                account_id = first_account['id']
            else:
                return jsonify({'error': 'No accounts found'}), 400
    note = data.get('note', '')
    with get_db_conn() as conn:
        cur = conn.execute('''INSERT INTO transactions 
                        (date, type, category, amount, currency, account_id, note)
                        VALUES (?, ?, ?, ?, ?, ?, ?)''',
                        (d.isoformat(), tx_type, category, amount, currency, account_id, note))
        tx_id = cur.lastrowid
        conn.commit()
    return jsonify({'id': tx_id, 'message': 'Transaction added successfully'})

@app.route('/api/exchange-rates', methods=['GET'])
def api_get_rates():
    return jsonify(get_exchange_rates())

@app.route('/api/exchange-rates', methods=['POST'])
def api_add_rate():
    data = request.json or {}
    from_currency = (data.get('from_currency') or '').upper()
    to_currency = (data.get('to_currency') or '').upper()
    rate = data.get('rate')
    if not from_currency or not to_currency or rate is None:
        return jsonify({'error': 'All fields are required (from_currency, to_currency, rate)'}), 400
    try:
        rate = float(rate)
        if rate <= 0:
            raise ValueError()
    except:
        return jsonify({'error': 'Invalid rate; must be positive number'}), 400
    if from_currency not in CURRENCIES or to_currency not in CURRENCIES:
        return jsonify({'error': 'Unsupported currency in from/to'}), 400
    with get_db_conn() as conn:
        conn.execute('''INSERT INTO exchange_rates (from_currency, to_currency, rate, date, source)
                        VALUES (?, ?, ?, ?, ?)''',
                     (from_currency, to_currency, rate, date.today().isoformat(), 'manual'))
        conn.commit()
    return jsonify({'message': 'Exchange rate added successfully'})

@app.route('/api/exchange-rates/update', methods=['POST'])
def api_update_rates():
    def update_rates():
        try:
            response = requests.get('https://api.exchangerate-api.com/v4/latest/USD', timeout=12)
            response.raise_for_status()
            data = response.json()
            rates = data.get('rates', {})
            today = date.today().isoformat()
            inserted = 0
            with get_db_conn() as conn:
                for currency in CURRENCIES:
                    if currency in rates and currency != 'USD':
                        conn.execute('''INSERT INTO exchange_rates 
                                       (from_currency, to_currency, rate, date, source)
                                       VALUES (?, ?, ?, ?, ?)''',
                                     ('USD', currency, float(rates[currency]), today, 'api'))
                        inserted += 1
                conn.commit()
            app.logger.info(f"update_rates: inserted {inserted} rates")
            return True
        except Exception as e:
            app.logger.exception("update_rates failed")
            return False
    thread = threading.Thread(target=update_rates, daemon=True)
    thread.start()
    return jsonify({'message': 'Exchange rates update started (background)'}), 202

@app.route('/api/dashboard')
def api_dashboard():
    """Get dashboard summary data including per-account balances (converted to account currency)."""
    with get_db_conn() as conn:
        # current month summary grouped by type and currency
        current_date = date.today()
        yr = current_date.year
        mo = current_date.month
        monthly_transactions = conn.execute('''
            SELECT type, SUM(amount) as total, currency
            FROM transactions 
            WHERE strftime('%Y', date) = ? AND strftime('%m', date) = ?
            GROUP BY type, currency
        ''', (str(yr), f"{mo:02d}")).fetchall()
        recent = conn.execute('''
            SELECT t.*, a.name as account_name 
            FROM transactions t 
            LEFT JOIN accounts a ON t.account_id = a.id 
            ORDER BY t.date DESC, t.id DESC 
            LIMIT 10
        ''').fetchall()
        accounts = conn.execute('SELECT * FROM accounts').fetchall()
        # compute simplified balances per account (sum income - expense; assume all amounts positive and type indicates sign)
        account_balances = []
        for acc in accounts:
            acc = dict(acc)
            acc_id = acc['id']
            acc_currency = acc['currency']
            rows = conn.execute('SELECT type, amount, currency FROM transactions WHERE account_id = ?', (acc_id,)).fetchall()
            balance = 0.0
            for r in rows:
                amt = float(r['amount'])
                src_curr = r['currency']
                # convert amount from src_curr to acc_currency using latest rate
                rate = get_latest_rate(src_curr, acc_currency)
                converted = amt * rate
                if r['type'] == 'expense':
                    balance -= converted
                else:
                    balance += converted
            acc['balance'] = round(balance, 2)
            account_balances.append(acc)
    return jsonify({
        'monthly_summary': [dict(r) for r in monthly_transactions],
        'recent_transactions': [dict(r) for r in recent],
        'accounts': account_balances
    })

@app.route('/api/reports/monthly/<int:year>/<int:month>')
def api_monthly_report(year, month):
    """Return monthly report data in JSON (same logic as earlier)."""
    transactions = get_transactions(limit=10000, account_id=None, year=year, month=month)
    income_total = sum(tx['amount'] for tx in transactions if tx['type'] == 'income')
    expense_total = sum(tx['amount'] for tx in transactions if tx['type'] == 'expense')
    expense_by_category = {}
    income_by_category = {}
    for tx in transactions:
        category = tx['category']
        amount = tx['amount']
        if tx['type'] == 'expense':
            expense_by_category[category] = expense_by_category.get(category, 0) + amount
        else:
            income_by_category[category] = income_by_category.get(category, 0) + amount
    return jsonify({
        'year': year,
        'month': month,
        'income_total': income_total,
        'expense_total': expense_total,
        'net': income_total - expense_total,
        'transaction_count': len(transactions),
        'expense_by_category': expense_by_category,
        'income_by_category': income_by_category,
        'transactions': transactions
    })

@app.route('/api/reports/monthly/<int:year>/<int:month>/pdf')
def api_monthly_report_pdf(year, month):
    """Generate PDF monthly report and return as downloadable file."""
    transactions = get_transactions(limit=10000, account_id=None, year=year, month=month)
    # build DataFrame for nice table
    if transactions:
        df = pd.DataFrame(transactions)
    else:
        df = pd.DataFrame(columns=['id','date','type','category','amount','currency','account_id','note','created_at','account_name'])
    income_total = df[df['type']=='income']['amount'].sum() if not df.empty else 0.0
    expense_total = df[df['type']=='expense']['amount'].sum() if not df.empty else 0.0
    # category pie for expenses
    expense_by_category = df[df['type']=='expense'].groupby('category')['amount'].sum() if not df.empty else pd.Series(dtype=float)
    # create PDF in memory
    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        # Page 1: summary text
        plt.figure(figsize=(8.27, 11.69))  # A4 portrait
        plt.axis('off')
        plt.title(f"Monthly Report: {year}-{month:02d}", fontsize=16)
        info_lines = [
            f"Income total: {income_total:.2f}",
            f"Expense total: {expense_total:.2f}",
            f"Net: {(income_total - expense_total):.2f}",
            f"Transactions: {len(df)}"
        ]
        for i, line in enumerate(info_lines):
            plt.text(0.1, 0.85 - i*0.06, line, fontsize=12, transform=plt.gcf().transFigure)
        pdf.savefig()
        plt.close()
        # Page 2: expense by category pie (if available)
        if not expense_by_category.empty:
            plt.figure(figsize=(8,6))
            expense_by_category.plot.pie(autopct='%1.1f%%', ylabel='', title='Expense by Category')
            pdf.savefig()
            plt.close()
        # Page 3+: transaction table(s) split if large
        if not df.empty:
            # render table as text in matplotlib (simple)
            rows_per_page = 25
            total_rows = len(df)
            pages = (total_rows + rows_per_page - 1) // rows_per_page
            for p in range(pages):
                start = p * rows_per_page
                end = min(start + rows_per_page, total_rows)
                sub = df.iloc[start:end]
                plt.figure(figsize=(11.69, 8.27))  # landscape for table
                plt.axis('off')
                tbl = plt.table(cellText=sub.values, colLabels=sub.columns, loc='center', cellLoc='left')
                tbl.auto_set_font_size(False)
                tbl.set_fontsize(8)
                tbl.scale(1, 1.2)
                plt.title(f"Transactions {start+1} - {end}")
                pdf.savefig()
                plt.close()
    buf.seek(0)
    filename = f"monthly_report_{year}_{month:02d}.pdf"
    return send_file(buf, as_attachment=True, download_name=filename, mimetype='application/pdf')

# Initialize database when app starts
init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
