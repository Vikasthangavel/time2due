import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv
import os
from datetime import datetime
from flask_bcrypt import Bcrypt

load_dotenv()
bcrypt = Bcrypt()

def connect():
    return mysql.connector.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        database=os.getenv('DB_NAME', 'time2cable'),
        user=os.getenv('DB_USER', 'root'),
        password=os.getenv('DB_PASSWORD', 'root')
    )

def get_customer_by_mobile_and_password(mobile_number, password):
    conn = connect()
    if not conn:
        return None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM customers WHERE mobile_number = %s", (mobile_number,))
        customer = cursor.fetchone()
        if customer and bcrypt.check_password_hash(customer['password'], password):
            return customer
        return None
    except Error as e:
        print(f"Error: {str(e)}")
        return None
    finally:
        cursor.close()
        conn.close()

def get_customer_by_id(customer_id):
    conn = connect()
    if not conn:
        return None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT id, box_number, mobile_number, name, email, plan_amount, balance, address, manager_id
            FROM customers WHERE id = %s
        """, (customer_id,))
        customer = cursor.fetchone()
        return customer
    except Error as e:
        print(f"Error: {str(e)}")
        return None
    finally:
        cursor.close()
        conn.close()

def get_payment_history(customer_id):
    conn = connect()
    if not conn:
        return None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT id, amount, payment_mode, payment_status, payment_date
            FROM payments
            WHERE customer_id = %s
            ORDER BY payment_date DESC
        """, (customer_id,))
        payments = cursor.fetchall()
        for payment in payments:
            if isinstance(payment['payment_date'], str):
                payment['payment_date'] = datetime.strptime(payment['payment_date'], '%Y-%m-%d %H:%M:%S')
        return payments
    except Error as e:
        print(f"Error fetching payment history: {str(e)}")
        return None
    finally:
        cursor.close()
        conn.close()

def update_customer_balance(customer_id, amount):
    conn = connect()
    if not conn:
        return False, "Database connection failed"
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT balance FROM customers WHERE id = %s", (customer_id,))
        customer = cursor.fetchone()
        if not customer:
            return False, "Customer not found"
        
        current_balance = float(customer['balance'])
        amount = float(amount)
        new_balance = current_balance + amount
        
        if new_balance < 0:
            return False, "Balance cannot be negative"
        
        cursor.execute(
            "UPDATE customers SET balance = %s WHERE id = %s",
            (new_balance, customer_id)
        )
        conn.commit()
        return True, "Balance updated successfully"
    except Error as e:
        conn.rollback()
        return False, f"Error updating balance: {str(e)}"
    finally:
        cursor.close()
        conn.close()

def add_payment(customer_id, manager_id, amount, payment_mode, payment_status, payment_reference):
    conn = connect()
    if not conn:
        return False, "Database connection failed"
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO payments (customer_id, manager_id, amount, payment_mode, payment_status, payment_reference)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (customer_id, manager_id, amount, payment_mode, payment_status, payment_reference))
        conn.commit()
        return True, "Payment recorded successfully"
    except Error as e:
        conn.rollback()
        return False, f"Error recording payment: {str(e)}"
    finally:
        cursor.close()
        conn.close()

def update_payment_status(payment_reference, status):
    conn = connect()
    if not conn:
        return False, "Database connection failed"
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE payments SET payment_status = %s WHERE payment_reference = %s",
            (status, payment_reference)
        )
        if cursor.rowcount == 0:
            return False, "Payment not found"
        conn.commit()
        return True, "Payment status updated successfully"
    except Error as e:
        conn.rollback()
        return False, f"Error updating payment status: {str(e)}"
    finally:
        cursor.close()
        conn.close()