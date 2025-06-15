from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_from_directory
from db import get_customer_by_mobile_and_password, get_customer_by_id, update_customer_balance, add_payment, get_payment_history, update_payment_status
from flask_bcrypt import Bcrypt
from dotenv import load_dotenv
import os
import requests
import json
from uuid import uuid4
from datetime import datetime
import pytz

app = Flask(__name__)

# Set timezone to Asia/Kolkata
IST = pytz.timezone('Asia/Kolkata')
# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'user_secret_key')  # Load from .env or use default
bcrypt = Bcrypt(app)

# Cashfree API configuration
CASHFREE_API_URL = "https://api.cashfree.com/pg"
CASHFREE_API_KEY = os.getenv('CASHFREE_API_KEY')
CASHFREE_API_SECRET = os.getenv('CASHFREE_API_SECRET')
PUBLIC_URL = os.getenv("PUBLIC_URL")
# Middleware for user authentication
def user_required(f):
    def wrap(*args, **kwargs):
        if 'logged_in' not in session or session['role'] != 'user':
            flash('Please log in as user to access this page.', 'error')
            return redirect(url_for('user_login'))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap
    
@app.route('/ads.txt')
def serve_ads_txt():
    return send_from_directory('.', 'ads.txt')
# User login
@app.route('/', methods=['GET', 'POST'])
def user_login():
    if request.method == 'POST':
        mobile_number = request.form['mobile_number']
        password = request.form['password']
        customer = get_customer_by_mobile_and_password(mobile_number, password)
        if customer:
            session['logged_in'] = True
            session['user_id'] = customer['id']
            session['role'] = 'user'
            flash('User login successful!', 'success')
            return redirect(url_for('user_dashboard'))
        else:
            flash('Invalid mobile number or password.', 'error')
    return render_template('user_login.html')

# User logout
@app.route('/user_logout')
def user_logout():
    session.pop('logged_in', None)
    session.pop('user_id', None)
    session.pop('role', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('user_login'))

# User dashboard
@app.route('/dashboard')
@user_required
def user_dashboard():
    customer_id = session['user_id']
    customer = get_customer_by_id(customer_id)
    payments = get_payment_history(customer_id)
    if not customer:
        flash('Failed to load customer data!', 'error')
        return render_template('user_dashboard.html', customer=None, payments=[])
    if not payments and payments != []:
        flash('Failed to fetch payment history.', 'error')
        payments = []
    return render_template('user_dashboard.html', customer=customer, payments=payments)
# Create Cashfree order
@app.route('/create_order', methods=['POST'])
@user_required
def create_order():
    customer_id = session['user_id']
    customer = get_customer_by_id(customer_id)
    if not customer:
        flash('Customer not found.', 'error')
        return redirect(url_for('user_dashboard'))

    try:
        amount = float(request.form['amount'])
        if amount <= 0:
            flash('Payment amount must be greater than 0.', 'error')
            return redirect(url_for('user_dashboard'))

        if amount > float(customer['balance']):
            flash('Payment amount cannot exceed current balance.', 'error')
            return redirect(url_for('user_dashboard'))

        order_id = f"order_{customer_id}_{uuid4().hex[:8]}"
        payload = {
            "order_amount": amount,
            "order_id": order_id,
            "order_currency": "INR",
            "customer_details": {
                "customer_id": str(customer['id']),
                "customer_name": customer['name'],
                "customer_email": customer['email'] or "noemail@example.com",
                "customer_phone": customer['mobile_number']
            },
            "order_meta": {
                "return_url": f"{PUBLIC_URL}/payment_return?order_id={{order_id}}",
                "notify_url": f"{PUBLIC_URL}/webhook"
            },
            "order_note": f"Payment for customer {customer['id']}"
        }

        headers = {
            "Content-Type": "application/json",
            "x-client-id": CASHFREE_API_KEY,
            "x-client-secret": CASHFREE_API_SECRET,
            "x-api-version": "2023-08-01"
        }

        response = requests.post(f"{CASHFREE_API_URL}/orders", headers=headers, json=payload)
        
        if response.status_code == 200:
            response_data = response.json()
            payment_session_id = response_data.get('payment_session_id')
            if payment_session_id:
                return jsonify({"payment_session_id": payment_session_id, "order_id": order_id})
            flash('Failed to get payment session ID.', 'error')
        else:
            flash(f"Failed to create order: {response.text}", 'error')
        return redirect(url_for('user_dashboard'))

    except ValueError:
        flash('Invalid payment amount.', 'error')
        return redirect(url_for('user_dashboard'))
    except Exception as e:
        flash(f"Error creating order: {str(e)}", 'error')
        return redirect(url_for('user_dashboard'))
@app.route('/payment_return')
@user_required
def payment_return():
    customer_id = session['user_id']
    customer = get_customer_by_id(customer_id)
    order_id = request.args.get('order_id')
    if not order_id:
        flash('Invalid order ID.', 'error')
        return redirect(url_for('user_dashboard'))

    headers = {
        "x-client-id": CASHFREE_API_KEY,
        "x-client-secret": CASHFREE_API_SECRET,
        "x-api-version": "2023-08-01"
    }

    try:
        response = requests.get(f"{CASHFREE_API_URL}/orders/{order_id}", headers=headers)
        if response.status_code == 200:
            order_data = response.json()
            if order_data.get('order_status') == 'PAID':
                amount = float(order_data.get('order_amount'))
                ist_timestamp = datetime.now(IST)
                success, message = add_payment(
                    customer_id=customer_id,
                    manager_id=customer['manager_id'],
                    amount=amount,
                    payment_mode='online',
                    payment_status='completed',
                    payment_reference=order_id,
                    payment_date=ist_timestamp,
                    created_at=ist_timestamp
                )
                if success:
                    success, message = update_customer_balance(customer_id, -amount)
                    flash(message, 'success' if success else 'error')
                else:
                    flash(message, 'error')
            else:
                flash('Payment not completed or failed.', 'error')
        else:
            flash('Failed to verify payment status.', 'error')
    except Exception as e:
        flash(f"Error verifying payment: {str(e)}", 'error')

    return redirect(url_for('user_dashboard'))

# Handle Cashfree webhook
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        payload = request.get_json()
        event = payload.get('event')
        order_id = payload.get('data', {}).get('order', {}).get('order_id')
        payment_status = payload.get('data', {}).get('payment', {}).get('payment_status')

        if not order_id or not event:
            return jsonify({"status": "error", "message": "Invalid webhook data"}), 400

        ist_timestamp = datetime.now(IST)
        if event == 'PAYMENT_SUCCESS' and payment_status == 'SUCCESS':
            customer_id = payload.get('data', {}).get('customer_details', {}).get('customer_id')
            amount = float(payload.get('data', {}).get('order', {}).get('order_amount'))
            success, message = update_payment_status(
                order_id=order_id,
                status='completed',
                payment_date=ist_timestamp,
                created_at=ist_timestamp
            )
            if success:
                success, message = update_customer_balance(customer_id, -amount)
                return jsonify({"status": "success", "message": message}), 200
            return jsonify({"status": "error", "message": message}), 500
        elif event == 'PAYMENT_FAILED' and payment_status == 'FAILED':
            success, message = update_payment_status(
                order_id=order_id,
                status='failed',
                payment_date=ist_timestamp,
                created_at=ist_timestamp
            )
            return jsonify({"status": "success" if success else "error", "message": message}), 200 if success else 500
        return jsonify({"status": "error", "message": "Unhandled event type"}), 400

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500 

if __name__ == '__main__':  
    app.run(debug=True, host='0.0.0.0', port=5003)
