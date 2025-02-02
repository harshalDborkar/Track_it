# functions.py

import sqlite3
import logging
import os
import json
import re
from datetime import date , datetime , timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import requests
from bs4 import BeautifulSoup
import time
import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Configure logging
logging.basicConfig(level=logging.INFO, filename='scraper.log',
                    format='%(asctime)s:%(levelname)s:%(message)s')

# Scraper functions
def create_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Run headlessly (no GUI)
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def scrape_amazon_product(url):
    driver = create_driver()
    product_details = {}

    try:
        logging.info(f"Navigating to Amazon URL: {url}")
        driver.get(url)
        
        wait = WebDriverWait(driver, 5)
        name_tag = wait.until(EC.presence_of_element_located((By.ID, 'productTitle')))
        product_details['name'] = name_tag.text.strip()
        logging.info(f"Product Name: {product_details['name']}")

        try:
            price_tag = driver.find_element(By.CSS_SELECTOR, 'span.a-price.aok-align-center.reinventPricePriceToPayMargin.priceToPay')
            product_details['price'] = price_tag.text.strip()
            logging.info(f"Price: {product_details['price']}")
        except:
            try:
                price_tag = driver.find_element(By.ID, 'priceblock_dealprice')
                product_details['price'] = price_tag.text.strip()
                logging.info(f"Price: {product_details['price']}")
            except:
                product_details['price'] = 'N/A'
                logging.warning("Price element not found.")

        try:
            image_tag = driver.find_element(By.ID, 'landingImage')
            product_details['image'] = image_tag.get_attribute('src')
            logging.info(f"Image URL: {product_details['image']}")
        except:
            product_details['image'] = 'N/A'
            logging.warning("Image element not found.")

        try:
            rating_tag = driver.find_element(By.XPATH, '//a[@class="a-popover-trigger a-declarative"]/span[@class="a-size-base a-color-base"]')
            star_rating = rating_tag.text.strip()  # Extracting the star rating
            product_details['star_rating'] = star_rating + " out of 5 stars"
            logging.info(f"Star Rating: {product_details['star_rating']}")
        except:
            product_details['star_rating'] = 'N/A'
            logging.warning("Star rating element not found.")

        # Extracting the total number of reviews
        try:
            reviews_tag = driver.find_element(By.ID, 'acrCustomerReviewText')
            product_details['reviews'] = reviews_tag.text.strip()
            logging.info(f"Reviews: {product_details['reviews']}")
        except:
            product_details['reviews'] = 'N/A'
            logging.warning("Reviews element not found.")

        product_details['link'] = url

    except Exception as err:
        logging.error(f"An error occurred while scraping Amazon: {err}")
    finally:
        driver.quit()

    return product_details

def find_flipkart_link(product_name):
    words = product_name.split()[:5]
    query = '+'.join(words)
    url = f'https://www.flipkart.com/search?q={query}'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3',
        'Accept-Language': 'en-US,en;q=0.5',
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        logging.info("Flipkart search request successful!")
        soup = BeautifulSoup(response.content, 'html.parser')
    
        logging.info(f"{url}")

        # Flipkart often has multiple product links; adjust as necessary
        for link in soup.find_all('a', href=True):
            if 'p/' in link['href']:
                product_link = 'https://www.flipkart.com' + link['href']
                logging.info(f"Found Flipkart product link: {product_link}")
                return product_link

        logging.warning("No product links found on Flipkart.")
        return None
    else:
        logging.error(f"Failed to retrieve the Flipkart search page. Status code: {response.status_code}")
        return None

def scrape_flipkart_product(url):
    driver = create_driver()
    product_details = {}

    try:
        logging.info(f"Navigating to Flipkart URL: {url}")
        driver.get(url)
        wait = WebDriverWait(driver, 2)

        try:
            close_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(),'✕')]")))
            close_button.click()
            logging.info("Login pop-up closed.")
        except:
            logging.info("No login pop-up detected.")

        name_tag = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'span.VU-ZEz')))
        product_details['name'] = name_tag.text.strip()
        logging.info(f"Product Name: {product_details['name']}")

        try:
            price_tag = driver.find_element(By.CSS_SELECTOR, 'div.Nx9bqj.CxhGGd')
            product_details['price'] = price_tag.text.strip()
            logging.info(f"Price: {product_details['price']}")
        except:
            product_details['price'] = 'N/A'
            logging.warning("Price element not found.")

        try:
            image_tag = driver.find_element(By.CSS_SELECTOR, 'img._396cs4')
            product_details['image'] = image_tag.get_attribute('src')
            logging.info(f"Image URL: {product_details['image']}")
        except:
            product_details['image'] = 'N/A'
            logging.warning("Image element not found.")

        product_details['link'] = url
            
    except Exception as err:
        logging.error(f"An error occurred while scraping Flipkart: {err}")
    finally:
        driver.quit()

    return product_details

def get_first_product_details(query):
    driver = create_driver()
    product_details = {}

    try:
        # Format the search query for Reliance Digital
        words = query.split()[:7]
        limited_query = '%20'.join(words)
        limited_query = re.sub(r'[(){}[\]]', '', limited_query)
        url = f"https://www.reliancedigital.in/search?q={limited_query}:relevance"
        logging.info(f"Visiting Reliance Digital URL: {url}")
        driver.get(url)
        time.sleep(5)  # Wait for the page to load

        wait = WebDriverWait(driver, 10)  # Increased wait time

        # Wait for the product elements to be present
        try:
            # Adjust selector for the product title
            title_element = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "p.sp__name"))  # Selector for product name
            )
            product_details['name'] = title_element.text.strip()
            logging.info(f"Product Title: {product_details['name']}")
        except Exception as e:
            product_details['name'] = 'N/A'
            logging.warning("Product title element not found.")

        # Extract price
        try:
            # Updated selector for price
            price_element = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.StyledPriceBoxM__PriceWrapper-sc-1l9ms6f-0 span:nth-of-type(2)"))  # Select the second span containing the price
            )
            product_details['price'] = price_element.text.strip()
            logging.info(f"Price: {product_details['price']}")
        except Exception as e:
            product_details['price'] = 'N/A'
            logging.warning("Price element not found.")
        
        try:
            # Selector for product link
            link_element = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.sp a[href*='/']"))  # Adjusted to find the link in the correct div
            )
            product_details['link'] = f"{link_element.get_attribute('href').strip()}"  # Complete the URL
            logging.info(f"Product Link: {product_details['link']}")
        except Exception as e:
            product_details['link'] = 'N/A'
            logging.warning("Product link element not found.")

    except Exception as e:
        logging.error("Error occurred while scraping Reliance Digital: " + str(e))

    finally:
        driver.quit()

    return product_details

# Watchlist management functions

import sqlite3
import json

def remove_item(email, columnname, srno):
    conn = sqlite3.connect('users.db')  # Ensure correct database path
    cursor = conn.cursor()
    
    try:
        # Fetch the current data from the correct column
        cursor.execute(f"SELECT {columnname} FROM User WHERE email = ?", (email,))
        cell_data = cursor.fetchone()

        if cell_data and cell_data[0]:  # Check if data exists and is not null
            try:
                data_list = json.loads(cell_data[0])  # Load existing JSON data
            except json.JSONDecodeError:
                data_list = []  # Initialize to empty if JSON is malformed
            
            if srno in data_list:
                data_list.remove(srno)  # Remove the item
                # Update the column in the User table
                cursor.execute(
                    f"UPDATE User SET {columnname} = ? WHERE email = ?", 
                    (json.dumps(data_list), email)
                )
                conn.commit()
                print(f"Item {srno} removed successfully from {columnname}.")
            else:
                print(f"Item {srno} not found in the list.")
        else:
            print("No data found for the given email or column.")
    
    except sqlite3.Error as e:
        print(f"Database Error: {e}")
    
    finally:
        conn.close()

def add_item(email, columnname, srno):
    conn = sqlite3.connect('users.db')  # Ensure correct database path
    cursor = conn.cursor()
    
    try:
        # Fetch the current data
        cursor.execute(f"SELECT {columnname} FROM user WHERE email = ?", (email,))
        cell_data = cursor.fetchone()

        if cell_data and cell_data[0]:  # Check if data exists and is not null
            try:
                data_list = json.loads(cell_data[0])  # Load existing JSON data
            except json.JSONDecodeError:
                data_list = []  # Initialize to empty if JSON is malformed
        else:
            data_list = []  # Initialize to empty if no data exists
        
        if srno not in data_list:
            data_list.append(srno)
            cursor.execute(
                f"UPDATE user SET {columnname} = ? WHERE email = ?", 
                (json.dumps(data_list), email)
            )
            conn.commit()
            print(f"Item {srno} added successfully.")
        else:
            print(f"Item {srno} is already in the list.")
    
    except sqlite3.Error as e:
        print(f"Error: {e}")
    
    finally:
        conn.close()

def does_user_have(usermail, columnname, srno):
    conn = get_users_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT {columnname} FROM user WHERE email = ?", (usermail,))
    data = cursor.fetchone()
    conn.close()

    if data[columnname] is None:
        return False

    data_list = json.loads(data[columnname])

    return True

# Notification functions

def notify(tablename):
    """
    Checks for price drops in the specified table.
    Returns a list of srnos with price drops.
    """
    conn = get_price_history_db_connection()
    cursor = conn.cursor()
    try:
        # Fetch all products
        cursor.execute(f"SELECT srno, name FROM {tablename}")
        products = cursor.fetchall()

        price_drops = []

        for product in products:
            srno = product['srno']
            name = product['name']

            # Fetch price history (assuming you have columns like date_1, date_2, ..., date_n)
            cursor.execute(f"PRAGMA table_info({tablename})")
            columns_info = cursor.fetchall()
            price_columns = [col['name'] for col in columns_info if col['name'].startswith('date_')]

            cursor.execute(f"SELECT {', '.join(price_columns)} FROM {tablename} WHERE srno = ?", (srno,))
            price_row = cursor.fetchone()

            # Extract and clean prices
            prices = [row for row in price_row if row is not None and row != 'N/A']
            cleaned_prices = []
            for price in prices:
                try:
                    cleaned_prices.append(float(price.replace('₹', '').replace(',', '').strip()))
                except:
                    continue

            # Check for price drops
            if len(cleaned_prices) < 2:
                continue  # Not enough data

            price_changes = np.diff(cleaned_prices)
            if any(change < 0 for change in price_changes):
                price_drops.append(srno)

        return price_drops

    except Exception as e:
        logging.error(f"Error in notify function: {e}")
        return []
    finally:
        conn.close()

def send_mail(to_email):
    """
    Sends an email notification to the specified email address.
    """
    from_email = "your_email@example.com"  # Replace with your email
    password = "your_email_password"        # Replace with your email password or app-specific password

    # Create a multipart email message
    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = "Price Drop Alert! 🎉"

    body = '''
    Hey there,

    Good news! 📉

    One of the products you're tracking has just dropped in price. Check your dashboard to see the updated price.

    Don't miss out on this great deal!

    Best regards,
    TrackIT Team
    '''

    # Attach the email body to the message
    msg.attach(MIMEText(body, 'plain'))

    try:
        # Connect to the Gmail SMTP server
        server = smtplib.SMTP('smtp.gmail.com', 587)  # For Gmail
        server.starttls()  # Upgrade to a secure connection
        server.login(from_email, password)  # Log in to your email account

        # Send the email
        server.send_message(msg)
        logging.info(f"Email sent successfully to {to_email}.")

    except Exception as e:
        logging.error(f"Failed to send email to {to_email}: {e}")

    finally:
        # Close the server connection
        server.quit()


# Database connection functions

def get_users_db_connection():
    """Connect to the users database."""
    basedir = os.path.abspath(os.path.dirname(__file__))
    users_db_path = os.path.join(basedir, 'users.db')
    conn = sqlite3.connect(users_db_path)
    conn.row_factory = sqlite3.Row
    return conn

def get_price_history_db_connection():
    """Connect to the price history database."""
    basedir = os.path.abspath(os.path.dirname(__file__))
    price_history_db_path = os.path.join(basedir, 'databases_price_history.db')
    conn = sqlite3.connect(price_history_db_path)
    conn.row_factory = sqlite3.Row
    return conn

# Functions to add new products to the databases

def add_new_amazon(link):
    """
    Adds a new Amazon product to the amazon_data table.
    """
    conn = get_price_history_db_connection()
    cursor = conn.cursor()

    try:
        # Scrape the product details
        product = scrape_amazon_product(link)
        name = product.get('name', 'N/A')
        price = product.get('price', 'N/A')

        # Insert into amazon_data
        cursor.execute("INSERT OR IGNORE INTO amazon_data (name, link) VALUES (?, ?)", (name, link))
        conn.commit()

        logging.info(f"Added new Amazon product: {name} with link: {link}")

    except Exception as e:
        logging.error(f"Error adding new Amazon product: {e}")
    finally:
        conn.close()

def add_new_flipkart(link):
    """
    Adds a new Flipkart product to the flipkart_data table.
    """
    conn = get_price_history_db_connection()
    cursor = conn.cursor()

    try:
        # Scrape the product details
        product = scrape_flipkart_product(link)
        name = product.get('name', 'N/A')
        price = product.get('price', 'N/A')

        # Insert into flipkart_data
        cursor.execute("INSERT OR IGNORE INTO flipkart_data (name, link) VALUES (?, ?)", (name, link))
        conn.commit()

        logging.info(f"Added new Flipkart product: {name} with link: {link}")

    except Exception as e:
        logging.error(f"Error adding new Flipkart product: {e}")
    finally:
        conn.close()

def make_list(tablename,columname):
    conn = get_users_db_connection()
    cursor=conn.cursor()
    cursor.execute(f"SELECT \"{columname}\" FROM  {tablename}")
    column_data = cursor.fetchall()
    data_list = [item[0] for item in column_data]
    

    return data_list


def send_alert_mail():
    user=make_list("user","email")
    nf=notify("flipkart_data")

    for i in user :
        for j in nf :
            if does_user_have(i,"srno_f",j):
                send_mail(i,"srno_f",j)
                break

    nf=notify("amazon_data")

    for i in user :
        for j in nf :
            if does_user_have(i,"srno_a",j):
                send_mail(i,"srno_a",j)
                break

def update_table_values_amazon():
    add_column("amazon_data")
    date_=str(date.today())

    conn = sqlite3.connect("databases_price_history.db")
    cursor = conn.cursor()
    column_data=[]

    try :
        cursor.execute(f"select link from amazon_data")
        rows=cursor.fetchall()
        column_data = [row[0] for row in rows]

        for i in column_data:
            price,name =scrape_amazon(i)
            
            query = f'''
                    update amazon_data
                    set  \"{date_}\" = ?
                    where link = ?
                    '''
            cursor.execute(query,(price,i))
            conn.commit()
    finally:
        # Close the database connection
        conn.close()

#fn to update flipkart_data table value ( will also add a column of todays date )

def update_table_values_flipkart():
    add_column("flipkart_data")
    date_=str(date.today())

    conn = sqlite3.connect("databases_price_history.db")
    cursor = conn.cursor()
    column_data=[]

    try :
        cursor.execute(f"select link from flipkart_data")
        rows=cursor.fetchall()
        column_data = [row[0] for row in rows]

        for i in column_data:
            price , name =scrape_flipkart(i)
            
            query = f'''
                    update flipkart_data
                    set  \"{date_}\" = ?
                    where link = ?
                    '''
            cursor.execute(query,(price,i))
            conn.commit()
    finally:
        # Close the database connection
        conn.close()


def add_column(tablename):

    date__= str(date.today())
    
    try:
        conn = sqlite3.connect("databases_price_history.db")
        cursor = conn.cursor()
        cursor.execute(f"""
            alter table {tablename}
            add column "{date__}" int default 0 """ 
        )
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
    
    finally:
        if conn:
            conn.close()

def scrape_flipkart(url):
    driver = create_driver()
    try:
        logging.info(f"Navigating to Flipkart URL: {url}")
        driver.get(url)
        
        wait = WebDriverWait(driver, 10)  # Increased wait time
        
        # Handle potential login pop-up
        try:
            logging.info("Checking for login pop-up...")
            close_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(),'✕')]")))
            close_button.click()
            logging.info("Login pop-up closed.")
        except:
            logging.info("No login pop-up detected.")
        
        # Wait for the product name to be present
        name_tag = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'span.VU-ZEz')))
        name = name_tag.text.strip()
        logging.info(f"Product Name: {name}")

        # Extract price using CSS_SELECTOR
        try:
            price_tag = driver.find_element(By.CSS_SELECTOR, 'div.Nx9bqj.CxhGGd')
            price = price_tag.text.strip()
            logging.info(f"Price: {price}")
        except:
            price = 'N/A'
            logging.warning("Price element not found.")
     

    except Exception as err:
        logging.error(f"An error occurred while scraping Flipkart: {err}")
        # Capture screenshot for debugging
        screenshot_path = os.path.join(os.getcwd(), "flipkart_error_screenshot.png")
        driver.save_screenshot(screenshot_path)
        logging.info(f"Screenshot saved to {screenshot_path}")
    finally:
        driver.quit()

    return price,name

# fn to scrape amazon

def scrape_amazon(url):
    driver = create_driver()
    product_details = {}
    

    try:
        logging.info(f"Navigating to Amazon URL: {url}")
        driver.get(url)
        
        wait = WebDriverWait(driver, 5)  # Increased wait time
        
        # Wait for the product title to be present
        name_tag = wait.until(EC.presence_of_element_located((By.ID, 'productTitle')))
        name = name_tag.text.strip()
        logging.info(f"Product Name: {name}")

        # Extract price using a more precise CSS selector
        try:
            price_tag = driver.find_element(By.CSS_SELECTOR, 'span.a-price.aok-align-center.reinventPricePriceToPayMargin.priceToPay')
            price = price_tag.text.strip()
            logging.info(f"Price: ₹{price}")
        except:
            try:
                price_tag = driver.find_element(By.ID, 'priceblock_dealprice')
                price = price_tag.text.strip()
                logging.info(f"Price: ₹{price}")
            except:
                price = 'N/A'
                logging.warning("Price element not found.")
        
    except Exception as err:
        logging.error(f"An error occurred while scraping Amazon: {err}")
        # Capture screenshot for debugging
        screenshot_path = os.path.join(os.getcwd(), "amazon_error_screenshot.png")
        driver.save_screenshot(screenshot_path)
        logging.info(f"Screenshot saved to {screenshot_path}")
    finally:
        driver.quit()
    return price,name



def db_to_excel(db_name, table_name, excel_file_name):
   
    conn = sqlite3.connect(db_name)
    
    try:
        query = f"SELECT * FROM {table_name}"
        df = pd.read_sql_query(query, conn)
        
        df.to_excel(excel_file_name, index=False)
        print(f"Table '{table_name}' has been successfully exported to '{excel_file_name}'.")
    
    except Exception as e:
        print(f"An error occurred: {e}")
    
    finally:
        conn.close()


def update():
    update_table_values_amazon()
    update_table_values_flipkart()
    print(notify("flipkart_data"))
    print(notify("amazon_data"))
    send_alert_mail()