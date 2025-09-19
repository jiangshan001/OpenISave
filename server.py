#!/usr/bin/env python3
import json
import sqlite3
import requests
from datetime import datetime, date
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse as urlparse
import os

# Database setup
def init_database():
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    
    # Create transactions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            type TEXT NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            currency TEXT NOT NULL,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create exchange rates table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS exchange_rates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_currency TEXT NOT NULL,
            to_currency TEXT NOT NULL,
            rate REAL NOT NULL,
            date TEXT NOT NULL,
            source TEXT DEFAULT 'api',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

class FinanceHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urlparse.urlparse(self.path)
        path = parsed_path.path
        
        # Serve static files
        if path == '/' or path == '/index.html':
            self.serve_file('index.html', 'text/html')
        elif path == '/api/transactions':
            self.handle_get_transactions()
        elif path == '/api/exchange-rates':
            self.handle_get_rates()
        elif path == '/api/dashboard':
            self.handle_get_dashboard()
        elif path.startswith('/api/reports/monthly/'):
            self.handle_get_monthly_report()
        else:
            self.send_error(404, f"Not Found: {self.path}")
    
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode('utf-8'))
        except:
            data = {}
        
        parsed_path = urlparse.urlparse(self.path)
        path = parsed_path.path
        
        if path == '/api/transactions':
            self.handle_add_transaction(data)
        elif path == '/api/exchange-rates/update':
            self.handle_update_rates()
        else:
            self.send_error(404, f"Not Found: {self.path}")
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def serve_file(self, filename, content_type):
        try:
            with open(filename, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_error(404, f"File not found: {filename}")
    
    def send_json_response(self, data, status_code=200):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode())
    
    def handle_get_transactions(self):
        try:
            conn = sqlite3.connect('finance.db')
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM transactions ORDER BY date DESC, created_at DESC')
            rows = cursor.fetchall()
            conn.close()
            
            transactions = []
            for row in rows:
                transactions.append({
                    'id': row[0],
                    'date': row[1],
                    'type': row[2],
                    'category': row[3],
                    'amount': row[4],
                    'currency': row[5],
                    'note': row[6] or ''
                })
            
            print(f"Returning {len(transactions)} transactions")
            self.send_json_response(transactions)
        except Exception as e:
            print(f"Error getting transactions: {e}")
            self.send_json_response({'error': str(e)}, 500)
    
    def handle_add_transaction(self, data):
        try:
            print(f"Adding transaction: {data}")
            conn = sqlite3.connect('finance.db')
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO transactions (date, type, category, amount, currency, note)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (data['date'], data['type'], data['category'], 
                  data['amount'], data['currency'], data.get('note', '')))
            
            transaction_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            print(f"Transaction added with ID: {transaction_id}")
            self.send_json_response({'id': transaction_id, 'success': True})
        except Exception as e:
            print(f"Error adding transaction: {e}")
            self.send_json_response({'error': str(e)}, 500)
    
    def handle_get_rates(self):
        try:
            conn = sqlite3.connect('finance.db')
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM exchange_rates ORDER BY created_at DESC')
            rows = cursor.fetchall()
            conn.close()
            
            rates = []
            for row in rows:
                rates.append({
                    'id': row[0],
                    'from_currency': row[1],
                    'to_currency': row[2],
                    'rate': row[3],
                    'date': row[4],
                    'source': row[5]
                })
            
            print(f"Returning {len(rates)} exchange rates")
            self.send_json_response(rates)
        except Exception as e:
            print(f"Error getting rates: {e}")
            self.send_json_response({'error': str(e)}, 500)
    
    def handle_update_rates(self):
        try:
            print("Updating exchange rates...")
            # Mock exchange rate data (replace with real API call if needed)
            rates_data = [
                {'from': 'USD', 'to': 'CNY', 'rate': 7.2345},
                {'from': 'EUR', 'to': 'CNY', 'rate': 7.8901},
                {'from': 'GBP', 'to': 'CNY', 'rate': 9.1234},
                {'from': 'CNY', 'to': 'USD', 'rate': 0.1383},
                {'from': 'CNY', 'to': 'EUR', 'rate': 0.1267},
                {'from': 'CNY', 'to': 'GBP', 'rate': 0.1096}
            ]
            
            conn = sqlite3.connect('finance.db')
            cursor = conn.cursor()
            
            # Clear old rates
            cursor.execute('DELETE FROM exchange_rates')
            
            # Insert new rates
            today = date.today().isoformat()
            for rate_info in rates_data:
                cursor.execute('''
                    INSERT INTO exchange_rates (from_currency, to_currency, rate, date, source)
                    VALUES (?, ?, ?, ?, 'api')
                ''', (rate_info['from'], rate_info['to'], rate_info['rate'], today))
            
            conn.commit()
            conn.close()
            
            print("Exchange rates updated successfully")
            self.send_json_response({'success': True})
        except Exception as e:
            print(f"Error updating rates: {e}")
            self.send_json_response({'error': str(e)}, 500)
    
    def handle_get_dashboard(self):
        try:
            conn = sqlite3.connect('finance.db')
            cursor = conn.cursor()
            
            # Get current month data
            current_date = datetime.now()
            current_month = f"{current_date.year}-{current_date.month:02d}"
            
            cursor.execute('''
                SELECT type, SUM(amount) as total
                FROM transactions 
                WHERE date LIKE ?
                GROUP BY type
            ''', (f"{current_month}%",))
            
            monthly_summary = [{'type': row[0], 'total': row[1]} for row in cursor.fetchall()]
            
            # Get recent transactions
            cursor.execute('SELECT * FROM transactions ORDER BY date DESC, created_at DESC LIMIT 10')
            rows = cursor.fetchall()
            
            recent_transactions = []
            for row in rows:
                recent_transactions.append({
                    'id': row[0],
                    'date': row[1],
                    'type': row[2],
                    'category': row[3],
                    'amount': row[4],
                    'currency': row[5],
                    'note': row[6] or ''
                })
            
            conn.close()
            
            dashboard_data = {
                'monthly_summary': monthly_summary,
                'recent_transactions': recent_transactions
            }
            
            print(f"Dashboard data: {len(monthly_summary)} summary items, {len(recent_transactions)} recent transactions")
            self.send_json_response(dashboard_data)
        except Exception as e:
            print(f"Error getting dashboard: {e}")
            self.send_json_response({'error': str(e)}, 500)
    
    def handle_get_monthly_report(self):
        try:
            path_parts = self.path.split('/')
            year = int(path_parts[4])
            month = int(path_parts[5])
            
            print(f"Generating report for {year}-{month:02d}")
            
            conn = sqlite3.connect('finance.db')
            cursor = conn.cursor()
            
            month_str = f"{year}-{month:02d}"
            
            # Get totals by type
            cursor.execute('''
                SELECT type, SUM(amount) as total
                FROM transactions 
                WHERE date LIKE ?
                GROUP BY type
            ''', (f"{month_str}%",))
            
            totals = dict(cursor.fetchall())
            
            # Get breakdown by category
            cursor.execute('''
                SELECT type, category, SUM(amount) as total
                FROM transactions 
                WHERE date LIKE ?
                GROUP BY type, category
            ''', (f"{month_str}%",))
            
            expense_by_category = {}
            income_by_category = {}
            
            for row in cursor.fetchall():
                if row[0] == 'expense':
                    expense_by_category[row[1]] = row[2]
                else:
                    income_by_category[row[1]] = row[2]
            
            conn.close()
            
            report_data = {
                'income_total': totals.get('income', 0),
                'expense_total': totals.get('expense', 0),
                'net': totals.get('income', 0) - totals.get('expense', 0),
                'expense_by_category': expense_by_category,
                'income_by_category': income_by_category
            }
            
            print(f"Report generated: Income={report_data['income_total']}, Expense={report_data['expense_total']}")
            self.send_json_response(report_data)
        except Exception as e:
            print(f"Error generating report: {e}")
            self.send_json_response({'error': str(e)}, 500)

if __name__ == '__main__':
    # Initialize database
    print("Initializing database...")
    init_database()
    
    # Start server
    server_address = ('127.0.0.1', 8000)
    httpd = HTTPServer(server_address, FinanceHandler)
    print(f"Starting server on http://127.0.0.1:8000")
    print("Press Ctrl+C to stop the server")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        httpd.server_close()