import mysql.connector
from mysql.connector import Error
from mysql.connector.pooling import MySQLConnectionPool
from dotenv import load_dotenv
import os
from datetime import datetime
from flask_bcrypt import Bcrypt
import pytz

IST = pytz.timezone('Asia/Kolkata')
load_dotenv()
bcrypt = Bcrypt()

# Database configuration from environment variables
db_config_writer = {
    'host': os.getenv('DB_HOST_WRITER', 'localhost'),
    'database': os.getenv('DB_NAME', 'time2cable'),
    'user': os.getenv('DB_USER_WRITER', 'root'),
    'password': os.getenv('DB_PASSWORD_WRITER', 'root')
}

db_config_reader = {
    'host': os.getenv('DB_HOST_READER', 'localhost'),
    'database': os.getenv('DB_NAME', 'time2cable'),
    'user': os.getenv('DB_USER_READER', 'root'),
    'password': os.getenv('DB_PASSWORD_READER', 'root')
}

# Create connection pools
writer_pool = MySQLConnectionPool(pool_name="writer_pool", pool_size=5, **db_config_writer)
reader_pool = MySQLConnectionPool(pool_name="reader_pool", pool_size=5, **db_config_reader)

def get_writer_connection():
    try:
        return writer_pool.get_connection()
    except Error as e:
        print(f"Error getting writer connection: {str(e)}")
        return None

def get_reader_connection():
    try:
        return reader_pool.get_connection()
    except Error as e:
        print(f"Error getting reader connection: {str(e)}")
        return None

def get_customer_by_mobile_and_password(mobile_number, password=None):
    conn = get_reader_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM customers WHERE mobile_number = %s", (mobile_number,))
        customer = cursor.fetchone()
        if password:
            if customer and bcrypt.check_password_hash(customer['password'], password):
                return customer
            return None
        return customer
    except Error as e:
        print(f"Error: {str(e)}")
        return None
    finally:
        cursor.close()
        conn.close()

def get_customer_by_id(customer_id):
    conn = get_reader_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT id, box_number, mobile_number, name, email, plan_amount, balance, address, manager_id, is_temp_password, password
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
    conn = get_reader_connection()
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
    conn = get_writer_connection()
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

def add_payment(customer_id, manager_id, amount, payment_mode, payment_status, payment_reference, payment_date=None, created_at=None):
    conn = get_writer_connection()
    if not conn:
        return False, "Database connection failed"
    try:
        cursor = conn.cursor()
        cursor.execute("SET time_zone = 'Asia/Kolkata'")
        ist_timestamp = datetime.now(IST)
        
        cursor.execute("""
            INSERT INTO payments (customer_id, manager_id, amount, payment_mode, payment_status, payment_reference, payment_date, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (customer_id, manager_id, amount, payment_mode, payment_status, payment_reference, ist_timestamp, ist_timestamp))
        conn.commit()
        return True, "Payment recorded successfully"
    except Error as e:
        conn.rollback()
        return False, f"Error recording payment: {str(e)}"
    finally:
        cursor.close()
        conn.close()

def update_payment_status(payment_reference, status):
    conn = get_writer_connection()
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

def update_customer_password(customer_id, hashed_password):
    conn = get_writer_connection()
    if not conn:
        return False, "Database connection failed"
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE customers SET password = %s, is_temp_password = %s WHERE id = %s",
            (hashed_password, False, customer_id)
        )
        if cursor.rowcount == 0:
            return False, "Customer not found"
        conn.commit()
        return True, "Password updated successfully"
    except Error as e:
        conn.rollback()
        return False, f"Error updating password: {str(e)}"
    finally:
        cursor.close()
        conn.close()

def store_otp(customer_id, otp, expires_at):
    conn = get_writer_connection()
    if not conn:
        return False, "Database connection failed"
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM otps WHERE customer_id = %s", (customer_id,))
        cursor.execute("""
            INSERT INTO otps (customer_id, otp, expires_at)
            VALUES (%s, %s, %s)
        """, (customer_id, otp, expires_at))
        conn.commit()
        return True, "OTP stored successfully"
    except Error as e:
        conn.rollback()
        return False, f"Error storing OTP: {str(e)}"
    finally:
        cursor.close()
        conn.close()

def verify_otp_route(customer_id, otp):
    conn = get_writer_connection()
    if not conn:
        return False, "Database connection failed"
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT otp, expires_at FROM otps WHERE customer_id = %s
        """, (customer_id,))
        otp_record = cursor.fetchone()
        if not otp_record:
            return False, "No OTP found for this customer"
        if otp_record['otp'] != otp:
            return False, "Invalid OTP"
        if datetime.now() > otp_record['expires_at']:
            return False, "OTP has expired"
        cursor.execute("DELETE FROM otps WHERE customer_id = %s", (customer_id,))
        conn.commit()
        return True, "OTP verified successfully"
    except Error as e:
        return False, f"Error verifying OTP: {str(e)}"
    finally:
        cursor.close()
        conn.close()
