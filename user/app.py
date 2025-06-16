from flask import Flask, render_template, request, redirect, send_from_directory, url_for, flash, session, jsonify
from db import get_customer_by_mobile_and_password, get_customer_by_id, update_customer_balance, add_payment, get_payment_history, update_payment_status, update_customer_password, store_otp, verify_otp_route
from flask_bcrypt import Bcrypt
from dotenv import load_dotenv
import os
import requests
import json
from uuid import uuid4
import smtplib
import string
import random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone, timedelta as dt_timedelta
import pytz
# Load environment variables
load_dotenv()

# Define IST timezone (UTC+5:30)
IST = pytz.timezone('Asia/Kolkata')

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'user_secret_key')
bcrypt = Bcrypt(app)

# Cashfree API configuration
CASHFREE_API_URL = "https://api.cashfree.com/pg"
CASHFREE_API_KEY = os.getenv('CASHFREE_API_KEY')
CASHFREE_API_SECRET = os.getenv('CASHFREE_API_SECRET')
# Email configuration
EMAIL_ADDRESS = os.getenv('EMAIL_ADDRESS')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
PUBLIC_URL = os.getenv("PUBLIC_URL")
@app.route('/ads.txt')
def serve_ads_txt():
    return send_from_directory('.', 'ads.txt')
def generate_otp(length=6):
    """Generate a random OTP."""
    characters = string.digits
    return ''.join(random.choice(characters) for _ in range(length))

def send_email(to_email, subject, body):
    """Send an email with the given subject and HTML body."""
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, to_email, msg.as_string())
        return True, "Email sent successfully"
    except Exception as e:
        return False, f"Failed to send email: {str(e)}"

# Middleware for user authentication
def user_required(f):
    def wrap(*args, **kwargs):
        if 'logged_in' not in session or session['role'] != 'user':
            flash('Please log in as user to access this page.', 'error')
            return redirect(url_for('user_login'))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap

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
            if customer['is_temp_password']:
                flash('You are using a temporary password. Please change it.', 'warning')
                return redirect(url_for('change_password'))
            flash('User login successful!', 'success')
            return redirect(url_for('user_dashboard'))
        else:
            flash('Invalid mobile number or password.', 'error')
    return render_template('user_login.html')

@app.route('/logout')
def user_logout():
    # logic for logging out (e.g., session.pop, redirect)
    return redirect(url_for('user_login'))

@app.route('/change_password', methods=['GET', 'POST'])
@user_required
def change_password():
    if request.method == 'POST':
        try:
            current_password = request.form['current_password']
            new_password = request.form['new_password']
            confirm_password = request.form['confirm_password']
        except KeyError as e:
            flash(f'Missing form field: {e.args[0]}', 'error')
            return render_template('change_password.html')
        
        customer_id = session['user_id']
        customer = get_customer_by_id(customer_id)
        
        if not customer:
            flash('Customer not found.', 'error')
            return redirect(url_for('user_dashboard'))
        
        if 'password' not in customer:
            flash('Customer password not available.', 'error')
            return render_template('change_password.html')
        
        if not bcrypt.check_password_hash(customer['password'], current_password):
            flash('Current password is incorrect.', 'error')
            return render_template('change_password.html')
        
        if new_password != confirm_password:
            flash('New passwords do not match.', 'error')
            return render_template('change_password.html')
        
        if len(new_password) < 8:
            flash('Password must be at least 8 characters long.', 'error')
            return render_template('change_password.html')
        
        hashed_new_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
        success, message = update_customer_password(customer_id, hashed_new_password)
        
        if success:
            flash('Password changed successfully!', 'success')
            return redirect(url_for('user_dashboard'))
        else:
            flash(message, 'error')
    
    return render_template('change_password.html')

# Forgot password
@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        mobile_number = request.form['mobile_number']
        customer = get_customer_by_mobile_and_password(mobile_number, None)
        if customer:
            otp = generate_otp()
            expires_at = datetime.now() + timedelta(minutes=5)  # Changed to 5 minutes
            success, message = store_otp(customer['id'], otp, expires_at)
            if success:
                # Send OTP via email
                subject = "Time2Due OTP for Password Reset"
                body = f"""
                <!DOCTYPE html>
                <html lang="en">
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>Time2Due Password Reset</title>
                    <style>
                        body {{
                            margin: 0;
                            padding: 0;
                            font-family: Arial, Helvetica, sans-serif;
                            background-color: #F3F4F6;
                        }}
                        .container {{
                            max-width: 600px;
                            margin: 20px auto;
                            background-color: #FFFFFF;
                            border-radius: 8px;
                            overflow: hidden;
                            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                        }}
                        .header {{
                            background-color: #1E3A8A;
                            color: #FFFFFF;
                            padding: 20px;
                            text-align: center;
                        }}
                        .header h1 {{
                            margin: 0;
                            font-size: 24px;
                        }}
                        .content {{
                            padding: 30px;
                            text-align: center;
                        }}
                        .content h2 {{
                            font-size: 20px;
                            color: #1E3A8A;
                            margin-bottom: 20px;
                        }}
                        .otp {{
                            font-size: 32px;
                            font-weight: bold;
                            color: #1E3A8A;
                            background-color: #EFF6FF;
                            padding: 15px;
                            border-radius: 6px;
                            display: inline-block;
                            margin: 20px 0;
                        }}
                        .content p {{
                            font-size: 16px;
                            color: #4B5563;
                            line-height: 1.5;
                            margin-bottom: 20px;
                        }}
                        .warning {{
                            color: #DC2626;
                            font-weight: bold;
                        }}
                        .footer {{
                            background-color: #F3F4F6;
                            padding: 20px;
                            text-align: center;
                            font-size: 14px;
                            color: #6B7280;
                        }}
                        .footer a {{
                            color: #1E3A8A;
                            text-decoration: none;
                        }}
                        @media only screen and (max-width: 600px) {{
                            .container {{
                                margin: 10px;
                            }}
                            .content {{
                                padding: 20px;
                            }}
                            .otp {{
                                font-size: 28px;
                            }}
                            .content h2 {{
                                font-size: 18px;
                            }}
                            .content p {{
                                font-size: 14px;
                            }}
                        }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <h1>Time2due</h1>
                        </div>
                        <div class="content">
                            <h2>Password Reset OTP</h2>
                            <p>Dear {customer['name']},</p>
                            <p>Your OTP for resetting your Time2due password is:</p>
                            <div class="otp">{otp}</div>
                            <p class="warning">This OTP is valid for 5 minutes only.</p>
                            <p>Please use it to reset your password. If you didn’t request this, contact our support team immediately.</p>
                        </div>
                        <div class="footer">
                            <p>Regards,<br>The Time2due Team</p>
                            <p><a href="mailto:info@time2due.com">info@time2due.com</a> | +91-8122762374</p>
                        </div>
                    </div>
                </body>
                </html>
                """
                email_success, email_message = send_email(customer['email'], subject, body)
                if email_success:
                    session['reset_customer_id'] = customer['id']
                    flash('OTP sent to your email.', 'success')
                    return redirect(url_for('verify_otp'))
                else:
                    flash(email_message, 'error')
            else:
                flash(message, 'error')
        else:
            flash('Mobile number not found.', 'error')
    return render_template('forgot_password.html')

@app.route('/verify_otp', methods=['GET', 'POST'])
def verify_otp():  # ✅ new name
    if 'reset_customer_id' not in session:
        flash('Invalid session. Please start the password reset process again.', 'error')
        return redirect(url_for('forgot_password'))
    
    if request.method == 'POST':
        otp = request.form['otp']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        if new_password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('verify_otp.html')
        if len(new_password) < 8:
            flash('Password must be at least 8 characters long.', 'error')
            return render_template('verify_otp.html')
        
        customer_id = session['reset_customer_id']
        success, message = verify_otp_route(customer_id, otp)  # Now correctly refers to db.verify_otp
        if success:
            hashed_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
            success, message = update_customer_password(customer_id, hashed_password)
            if success:
                session.pop('reset_customer_id', None)
                flash('Password reset successfully! Please log in.', 'success')
                return redirect(url_for('user_login'))
            else:
                flash(message, 'error')
        else:
            flash(message, 'error')
    return render_template('verify_otp.html')


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
@app.route('/create_order', methods=['POST'])
@user_required
def create_order():
    customer_id = session['user_id']
    customer = get_customer_by_id(customer_id)
    if not customer:
        return jsonify({'error': 'Customer not found'}), 404

    try:
        amount = float(request.form.get('amount'))
        if amount <= 0:
            return jsonify({'error': 'Payment amount must be greater than 0'}), 400
        if amount > float(customer['balance']):
            return jsonify({'error': 'Payment amount cannot exceed current balance'}), 400

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
            return jsonify({'error': 'Failed to get payment session ID'}), 500
        else:
            return jsonify({'error': f"Failed to create order: {response.text}"}), response.status_code

    except ValueError:
        return jsonify({'error': 'Invalid payment amount'}), 400
    except Exception as e:
        return jsonify({'error': f"Error creating order: {str(e)}"}), 500

@app.route('/payment_return')
@user_required
def payment_return():
    customer_id = session['user_id']
    customer = get_customer_by_id(customer_id)
    order_id = request.args.get('order_id')
    if not order_id:
        return jsonify({'error': 'Invalid order ID'}), 400

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
                    return jsonify({'message': message, 'status': 'success'}), 200
                return jsonify({'error': message}), 500
            else:
                return jsonify({'error': 'Payment not completed or failed'}), 400
        else:
            return jsonify({'error': 'Failed to verify payment status'}), response.status_code
    except Exception as e:
        return jsonify({'error': f"Error verifying payment: {str(e)}"}), 500

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
    app.run(debug=True, port=5003)
