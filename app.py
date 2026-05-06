from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
import time
import logging

# Prometheus
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

# CloudWatch
import boto3
from watchtower import CloudWatchLogHandler

app = Flask(__name__)
app.secret_key = 'super_secret_premium_key'

DATABASE = 'ecommerce.db'

# -------------------------------
# 🟢 PROMETHEUS METRICS
# -------------------------------
REQUEST_COUNT = Counter(
    'app_requests_total',
    'Total HTTP Requests',
    ['method', 'endpoint', 'http_status']
)

REQUEST_LATENCY = Histogram(
    'app_request_latency_seconds',
    'Request latency',
    ['endpoint']
)

# -------------------------------
# 🔵 CLOUDWATCH SETUP
# -------------------------------
cloudwatch = boto3.client('cloudwatch', region_name='ap-south-1')

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

try:
    cw_handler = CloudWatchLogHandler(log_group='ecommerce-app-logs')
    logger.addHandler(cw_handler)
except Exception as e:
    print("CloudWatch logging setup failed:", e)

# -------------------------------
# DATABASE FUNCTIONS
# -------------------------------
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    if not os.path.exists(DATABASE):
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                price REAL NOT NULL,
                image_url TEXT NOT NULL
            )
        ''')

        demo_products = [
            ('Acoustic Noise Cancelling Headphones', 'Premium wireless headphones with industry-leading noise cancellation.', 299.99, 'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=500&q=80'),
            ('Mechanical Gaming Keyboard', 'Tactile switches, RGB lighting, aluminum frame.', 149.99, 'https://images.unsplash.com/photo-1595225476474-87563907a212?w=500&q=80'),
            ('4K Action Camera', 'Waterproof, records 4K at 60fps.', 199.99, 'https://images.unsplash.com/photo-1526170375885-4d8ecf77b99f?w=500&q=80'),
            ('Smart Fitness Watch', 'Track heart rate, sleep, activity.', 249.99, 'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=500&q=80'),
            ('Power Bank', '10000mAh fast charging.', 49.99, 'https://images.unsplash.com/photo-1609091839311-d5365f9ff1c5?w=500&q=80'),
            ('Desk Lamp', 'LED lamp with USB port.', 79.99, 'https://images.unsplash.com/photo-1507473885765-e6ed057f782c?w=500&q=80')
        ]

        cursor.executemany(
            'INSERT INTO products (name, description, price, image_url) VALUES (?, ?, ?, ?)',
            demo_products
        )
        conn.commit()
        conn.close()

# -------------------------------
# REQUEST HOOKS (SRE CORE)
# -------------------------------
@app.before_request
def before_request():
    init_db()
    request.start_time = time.time()

    if 'cart' not in session:
        session['cart'] = []

@app.after_request
def after_request(response):
    latency = time.time() - request.start_time

    # 🟢 Prometheus metrics
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.path,
        http_status=response.status_code
    ).inc()

    REQUEST_LATENCY.labels(
        endpoint=request.path
    ).observe(latency)

    # 🔵 CloudWatch metrics
    try:
        cloudwatch.put_metric_data(
            Namespace='EcommerceApp',
            MetricData=[
                {
                    'MetricName': 'RequestCount',
                    'Dimensions': [{'Name': 'Endpoint', 'Value': request.path}],
                    'Value': 1,
                    'Unit': 'Count'
                },
                {
                    'MetricName': 'Latency',
                    'Dimensions': [{'Name': 'Endpoint', 'Value': request.path}],
                    'Value': latency,
                    'Unit': 'Seconds'
                }
            ]
        )
    except Exception as e:
        print("CloudWatch metric error:", e)

    # 🔵 CloudWatch logs
    logger.info(f"{request.method} {request.path} {response.status_code} {latency:.4f}s")

    return response

# -------------------------------
# ROUTES
# -------------------------------
@app.route('/')
def index():
    conn = get_db()
    products = conn.execute('SELECT * FROM products').fetchall()
    conn.close()
    return render_template('index.html', products=products)

@app.route('/product/<int:product_id>')
def product(product_id):
    conn = get_db()
    product = conn.execute(
        'SELECT * FROM products WHERE id = ?', (product_id,)
    ).fetchone()
    conn.close()

    if product is None:
        return "Product not found", 404

    return render_template('product.html', product=product)

@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    cart = session.get('cart', [])
    cart.append(product_id)
    session['cart'] = cart
    flash('Product added!')
    return redirect(request.referrer or url_for('index'))

@app.route('/cart')
def cart():
    cart_ids = session.get('cart', [])
    cart_items = []
    total = 0

    if cart_ids:
        conn = get_db()
        placeholders = ','.join('?' for _ in cart_ids)
        query = f'SELECT * FROM products WHERE id IN ({placeholders})'
        products = conn.execute(query, cart_ids).fetchall()

        from collections import Counter
        counts = Counter(cart_ids)
        product_dict = {p['id']: p for p in products}

        for pid, qty in counts.items():
            if pid in product_dict:
                p = product_dict[pid]
                subtotal = p['price'] * qty
                cart_items.append({
                    'product': p,
                    'quantity': qty,
                    'subtotal': subtotal
                })
                total += subtotal

        conn.close()

    return render_template('cart.html', cart_items=cart_items, total=total)

@app.route('/clear_cart', methods=['POST'])
def clear_cart():
    session['cart'] = []
    flash('Cart cleared!')
    return redirect(url_for('cart'))

# 🟢 PROMETHEUS ENDPOINT
@app.route('/metrics')
def metrics():
    return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}

# -------------------------------
# RUN
# -------------------------------
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)