# app.py

import os
import re
import sqlite3
import json
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from functions import *
from predictor import PricePredictionModel
import pandas as pd
import logging
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Replace with a strong, random secret key

# Define the path to the SQLite databases
basedir = os.path.abspath(os.path.dirname(__file__))
users_db_path = os.path.join(basedir, 'users.db')
price_history_db_path = os.path.join(basedir, 'databases_price_history.db')

def get_users_db_connection():
    conn = sqlite3.connect(users_db_path)
    conn.row_factory = sqlite3.Row
    return conn

def get_price_history_db_connection():
    conn = sqlite3.connect(price_history_db_path)
    conn.row_factory = sqlite3.Row
    return conn

def get_username(email):
    """Extracts the username from an email address."""
    return email.split('@')[0] if '@' in email else email

# Create the `amazon_data` table if it doesn't exist
def initialize_database():
    conn = get_price_history_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS amazon_data (
            srno INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            link TEXT NOT NULL UNIQUE,
            "2024-10-08" INTEGER DEFAULT 0,
            "2024-10-09" INTEGER DEFAULT 0,
            "2024-10-10" INTEGER DEFAULT 0,
            "2024-10-11" INTEGER DEFAULT 0,
            "2024-10-12" INTEGER DEFAULT 0,
            "2024-10-13" INTEGER DEFAULT 0,
            "2024-10-14" INTEGER DEFAULT 0,
            "2024-10-15" INTEGER DEFAULT 0,
            "2024-10-16" INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

initialize_database()


# Initialize Logger
logging.basicConfig(level=logging.INFO)

# Load data and initialize model
try:
    # Connect to the database and load data
    conn = sqlite3.connect(price_history_db_path)
    query = "SELECT * FROM amazon_data"
    dataset = pd.read_sql_query(query, conn)
    conn.close()

    # Initialize prediction model
    predictor = PricePredictionModel(dataset)
    predictor_dataset = predictor.preprocess_data()
    predictor.train_model()  # Train the model with the cleaned dataset

    logging.info("PricePredictionModel initialized successfully.")
except Exception as e:
    logging.error(f"Failed to initialize PricePredictionModel: {e}")
    predictor = None


@app.route('/')
def index():
    return render_template('index.html', title="TrackIT")

@app.route('/scrape', methods=['POST'])
def scrape():
    amazon_product_url = request.form['url']
    amazon_data = scrape_amazon_product(amazon_product_url)
    product_name = amazon_data.get('name', 'N/A')
    current_price = amazon_data['price']
    product_link = amazon_data['link']
    today_date = datetime.now().strftime('%Y-%m-%d')

    prediction = "Prediction unavailable"

    conn = get_price_history_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(f'ALTER TABLE amazon_data ADD COLUMN "{today_date}" INTEGER DEFAULT 0')
        conn.commit()
    except sqlite3.OperationalError:
        # Column already exists
        pass

    prediction_text = "Prediction unavailable"

    try:
        cursor.execute('SELECT * FROM amazon_data WHERE name = ?', (product_name,))
        product = cursor.fetchone()

        if product:
            # Update today's price for the product
            cursor.execute(f'UPDATE amazon_data SET "{today_date}" = ? WHERE name = ?', (current_price, product_name))
            conn.commit()

            # Extract price columns
            product_prices = [product[col] for col in product.keys() if col.startswith("2024-")]

            # Clean and filter numeric prices
            def clean_price(price):
                if isinstance(price, str):
                    price = price.replace('₹', '').replace(',', '').strip()
                try:
                    return float(price)
                except (ValueError, TypeError):
                    return None

            cleaned_prices = [clean_price(price) for price in product_prices if price is not None]

            # Check if sufficient data is available for prediction
            if len(cleaned_prices) >= 2 and predictor:
                avg_price = sum(cleaned_prices) / len(cleaned_prices)
                price_std = (sum((x - avg_price) ** 2 for x in cleaned_prices) / len(cleaned_prices)) ** 0.5
                price_change = (max(cleaned_prices) - min(cleaned_prices)) / max(cleaned_prices)
                input_features = [price_std, price_change]
                try:
                    prediction = predictor.predict(input_features)
                except Exception as e:
                    logging.error(f"Error during prediction: {e}")
                    prediction = -1  # Default value
            else:
                logging.warning("Insufficient data for prediction.")
                prediction = -1  # Default value

            
        else:
            # Insert new product data into the database
            cursor.execute(f'''
                INSERT INTO amazon_data (name, link, "{today_date}")
                VALUES (?, ?, ?)
            ''', (product_name, product_link, current_price))
            conn.commit()

    except Exception as e:
        logging.error(f"Error processing prediction: {e}")


    # Fetch additional details
    flipkart_product_url = find_flipkart_link(product_name)
    flipkart_data = scrape_flipkart_product(flipkart_product_url) if flipkart_product_url else {}
    reliance_product_data = get_first_product_details(product_name)

    conn.close()
    prediction_value = int(prediction) if str(prediction).isdigit() else -1
    return render_template(
        'result.html',
        amazon=amazon_data,
        flipkart=flipkart_data,
        reliance=reliance_product_data,
        prediction=prediction_value
        )
        
@app.route('/track', methods=['POST'])
def track():
    # Get product details from the form
    amazon_link = request.form.get('amazon_link')
    flipkart_link = request.form.get('flipkart_link')
    reliance_link = request.form.get('reliance_link')

    # Extract SRNO from the links
    srno_a = None
    srno_f = None

    if amazon_link:
        srno_a = get_srno_from_link(amazon_link, 'amazon_data')
    if flipkart_link:
        srno_f = get_srno_from_link(flipkart_link, 'flipkart_data')

    if not session.get('user_id'):
        # Store the intended action in session to redirect after login
        session['next'] = request.referrer
        flash('Please log in to track products.', 'warning')
        return redirect(url_for('login'))

    user_email = session.get('email')

    if srno_a:
        add_item(user_email, "srno_a", srno_a)
    if srno_f:
        add_item(user_email, "srno_f", srno_f)

    flash('Product added to your watchlist.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']

        logging.info(f"Attempting to sign up with email: {email}")  # Debugging statement

        # Validate email format
        email_regex = r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'
        if not re.match(email_regex, email):
            flash('Invalid email format.', 'danger')
            return render_template('signup.html', title="Sign Up", button_text="Sign Up")

        # Validate password length
        if len(password) < 8:
            flash('Password must be at least 8 characters long.', 'danger')
            return render_template('signup.html', title="Sign Up", button_text="Sign Up")

        conn = get_users_db_connection()
        cursor = conn.cursor()

        # Check if user already exists
        cursor.execute("SELECT * FROM User WHERE email = ?", (email,))
        existing_user = cursor.fetchone()
        if existing_user:
            logging.warning(f"User with email {email} already exists.")
            flash('Email already used. Please log in.', 'warning')
            conn.close()
            return redirect(url_for('login'))

        # Create new user
        try:
            hashed_password = generate_password_hash(password)
            cursor.execute("INSERT INTO User (email, password) VALUES (?, ?)", (email, hashed_password))
            conn.commit()
            logging.info(f"User {email} added to the database.")
            flash('Sign up successful! You can log in now.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            conn.rollback()
            flash('An error occurred during sign up. Please try again.', 'danger')
            logging.error(f"Error during sign up: {e}")  # For debugging purposes
            return render_template('signup.html', title="Sign Up", button_text="Sign Up")
        finally:
            conn.close()

    return render_template('signup.html', title="Sign Up", button_text="Sign Up")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']

        conn = get_users_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM User WHERE email = ?", (email,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['email'] = user['email']  # Store email in session
            flash('Log in successful!', 'success')
            # Redirect to 'next' if exists
            next_page = session.pop('next', None)
            if next_page:
                return redirect(next_page)
            return redirect(url_for('dashboard'))
        else:
            flash('Login failed. Check your email and password.', 'danger')
    return render_template('login.html', title="Log In", button_text="Log In")

@app.route('/dashboard', methods=['GET'])
def dashboard():
    user_id = session.get('user_id')
    user_email = session.get('email')
    if not user_id:
        flash('Please log in to access the dashboard.', 'warning')
        return redirect(url_for('login'))

    conn = get_users_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT email FROM User WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()

    if not user:
        flash('User not found. Please log in again.', 'danger')
        return redirect(url_for('login'))

    username = get_username(user['email'])

    # Fetch user's watchlist
    conn_price = get_users_db_connection()
    cursor_price = conn_price.cursor()
    cursor_price.execute("SELECT * FROM user WHERE email = ?", (user_email,))
    watchlist = cursor_price.fetchone()
    conn_price.close()

    watchlist_details = fetch_watchlist_details(watchlist) if watchlist else {'amazon': [], 'flipkart': []}

    return render_template('dashboard.html', username=username, watchlist=watchlist_details)

@app.route('/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    session.pop('email', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

def get_srno_from_link(link, table):
    """Retrieve the srno from the specified table based on the product link."""
    conn = get_price_history_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT srno FROM {table} WHERE link = ?", (link,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return result['srno']
    return None

@app.template_filter('fromjson')
def fromjson_filter(json_str):
    """Custom filter to parse JSON strings."""
    try:
        return json.loads(json_str)
    except:
        return []

def fetch_watchlist_details(watchlist):
    """Fetch detailed information about the products in the user's watchlist."""
    watchlist_details = {'amazon': [], 'flipkart': []}
    conn_price = get_users_db_connection()
    cursor_price = conn_price.cursor()

    conn_data = get_price_history_db_connection()
    cursor_data = conn_data.cursor()

    if watchlist['srno_a']:
        try:
            srnos_a = json.loads(watchlist['srno_a'])
            for srno in srnos_a:
                cursor_data.execute("SELECT * FROM amazon_data WHERE srno = ?", (srno,))
                product = cursor_data.fetchone()
                if product:
                    watchlist_details['amazon'].append(product)
        except Exception as e:
            logging.error(f"Error parsing srno_a: {e}")

    if watchlist['srno_f']:
        try:
            srnos_f = json.loads(watchlist['srno_f'])
            for srno in srnos_f:
                cursor_data.execute("SELECT * FROM flipkart_data WHERE srno = ?", (srno,))
                product = cursor_data.fetchone()
                if product:
                    watchlist_details['flipkart'].append(product)
        except Exception as e:
            logging.error(f"Error parsing srno_f: {e}")

    conn_price.close()
    return watchlist_details

# Notification Route (Optional: Trigger manually)
@app.route('/send_notifications', methods=['GET'])
def send_notifications():
    """
    Manual route to trigger notifications.
    You can access this route to send notifications to all users.
    """
    price_drops_amazon = notify("amazon_data")
    price_drops_flipkart = notify("flipkart_data")

    conn_users = get_users_db_connection()
    cursor_users = conn_users.cursor()
    cursor_users.execute("SELECT * FROM user")
    user_carts = cursor_users.fetchall()
    conn_users.close()

    for cart in user_carts:
        user_email = cart['user_mail']
        # Check Flipkart notifications
        if cart['srno_f']:
            srnos_f = json.loads(cart['srno_f'])
            for srno in price_drops_flipkart:
                if srno in srnos_f:
                    send_mail(user_email)
                    break
        # Check Amazon notifications
        if cart['srno_a']:
            srnos_a = json.loads(cart['srno_a'])
            for srno in price_drops_amazon:
                if srno in srnos_a:
                    send_mail(user_email)
                    break

    flash('Notifications have been sent successfully.', 'success')
    return redirect(url_for('dashboard'))

# Route to remove item from watchlist
@app.route('/remove_watchlist', methods=['POST'])
def remove_watchlist():
    user_email = session.get('email')  # Get the logged-in user's email
    platform = request.form.get('platform')  # 'amazon' or 'flipkart'
    srno = request.form.get('srno')  # The serial number of the product to remove

    # Debugging print
    print(f"Form data: {request.form}")
    print(f"Platform: {platform}")
    print(f"Serial Number: {srno}")

    if not user_email:
        flash('Please log in to remove products from your watchlist.', 'warning')
        return redirect(url_for('login'))

    if platform == "amazon":
        columnname = "srno_A"
    elif platform == "flipkart":
        columnname = "srno_f"
    else:
        flash('Invalid platform selected.', 'danger')
        return redirect(url_for('dashboard'))

    try:
        remove_item(user_email, columnname, int(srno))
        flash('Product removed from your watchlist.', 'success')
    except Exception as e:
        print(f"Error during removal: {e}")
        flash('Failed to remove product from your watchlist.', 'danger')

    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True)
