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

# -------------------------------------------------
# 🟢 PROMETHEUS METRICS
# -------------------------------------------------

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

# -------------------------------------------------
# 🔵 CLOUDWATCH SETUP
# -------------------------------------------------

AWS_REGION = 'ap-south-1'

# CloudWatch Metrics Client
cloudwatch = boto3.client(
    'cloudwatch',
    region_name=AWS_REGION
)

# CloudWatch Logs Client
logs_client = boto3.client(
    'logs',
    region_name=AWS_REGION
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

try:
    # CloudWatch Log Handler
    cw_handler = CloudWatchLogHandler(
        boto3_client=logs_client,
        log_group='ecommerce-app-logs'
    )

    logger.addHandler(cw_handler)

    print("✅ CloudWatch logging initialized successfully")

except Exception as e:
    print("❌ CloudWatch logging setup failed:", e)

# -------------------------------------------------
# DATABASE FUNCTIONS
# -------------------------------------------------

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
            (
                'Acoustic Noise Cancelling Headphones',
                'Premium wireless headphones with industry-leading noise cancellation. 30-hour battery life.',
                299.99,
                'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=500&q=80'
            ),
            (
                'Mechanical Gaming Keyboard',
                'Tactile switches, RGB lighting, aluminum frame. Custom programmable keys.',
                149.99,
                'https://images.unsplash.com/photo-1595225476474-87563907a212?w=500&q=80'
            ),
            (
                '4K Action Camera',
                'Waterproof, records 4K at 60fps. Built-in stabilization.',
                199.99,
                'https://images.unsplash.com/photo-1526170375885-4d8ecf77b99f?w=500&q=80'
            ),
            (
                'Smart Fitness Watch',
                'Track heart rate, sleep, activity. Water resistant design.',
                249.99,
                'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=500&q=80'
            ),
            (
                'Power Bank',
                '10000mAh fast charging. Dual USB outputs.',
                49.99,
                'https://images.unsplash.com/photo-1609091839311-d5365f9ff1c5?w=500&q=80'
            ),
            (
                'Desk Lamp',
                'LED lamp with USB port. 5 brightness levels.',
                79.99,
                'https://images.unsplash.com/photo-1507473885765-e6ed057f782c?w=500&q=80'
            ),
            (
                'Wireless Mouse',
                'Precision tracking, ergonomic design. 2-year battery life.',
                59.99,
                'https://images.unsplash.com/photo-1527814050087-3793815479db?w=500&q=80'
            ),
            (
                'USB-C Hub',
                '7-in-1 multi-port hub. Supports 4K video output.',
                89.99,
                'https://images.unsplash.com/photo-1625948515291-69613efd103f?w=500&q=80'
            ),
            (
                'Portable SSD 1TB',
                'Fast transfer speeds, compact design. USB 3.2 Gen 2.',
                149.99,
                'https://images.unsplash.com/photo-1597872200969-2b65d56bd16b?w=500&q=80'
            ),
            (
                'Wireless Charger',
                'Fast charging pad. Works with all Qi devices.',
                34.99,
                'https://images.unsplash.com/photo-1591954191477-d625d51b5c2e?w=500&q=80'
            ),
            (
                '4K Webcam',
                'Crystal clear video. Built-in microphone with noise cancellation.',
                179.99,
                'https://images.unsplash.com/photo-1598327105666-5b89351aff97?w=500&q=80'
            ),
            (
                'Laptop Stand',
                'Adjustable aluminum stand. Supports up to 17 inch laptops.',
                44.99,
                'https://images.unsplash.com/photo-1587829191301-f0e7e2d9c2a0?w=500&q=80'
            ),
            (
                'Mechanical Pen Display',
                '15.6 inch display, pressure sensitive. Perfect for design work.',
                399.99,
                'https://images.unsplash.com/photo-1612198188060-c7c2a3b66eae?w=500&q=80'
            ),
            (
                'Premium Cable Organizer',
                'Silicone cable management. Keeps desk tidy.',
                24.99,
                'https://images.unsplash.com/photo-1592849385229-26ec4cf57d13?w=500&q=80'
            ),
            (
                'Smart LED Strip Lights',
                'RGB color changing. App controlled, music sync.',
                69.99,
                'https://images.unsplash.com/photo-1570902522859-dfd71a099a0c?w=500&q=80'
            )
        ]

        cursor.executemany(
            '''
            INSERT INTO products
            (name, description, price, image_url)
            VALUES (?, ?, ?, ?)
            ''',
            demo_products
        )

        conn.commit()
        conn.close()

# -------------------------------------------------
# REQUEST HOOKS (SRE CORE)
# -------------------------------------------------

@app.before_request
def before_request():
    init_db()

    request.start_time = time.time()

    if 'cart' not in session:
        session['cart'] = []

@app.after_request
def after_request(response):

    latency = time.time() - request.start_time

    # -------------------------------------------------
    # 🟢 PROMETHEUS METRICS
    # -------------------------------------------------

    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.path,
        http_status=response.status_code
    ).inc()

    REQUEST_LATENCY.labels(
        endpoint=request.path
    ).observe(latency)

    # -------------------------------------------------
    # 🔵 CLOUDWATCH METRICS
    # -------------------------------------------------

    try:
        cloudwatch.put_metric_data(
            Namespace='EcommerceApp',
            MetricData=[
                {
                    'MetricName': 'RequestCount',
                    'Dimensions': [
                        {
                            'Name': 'Endpoint',
                            'Value': request.path
                        }
                    ],
                    'Value': 1,
                    'Unit': 'Count'
                },
                {
                    'MetricName': 'Latency',
                    'Dimensions': [
                        {
                            'Name': 'Endpoint',
                            'Value': request.path
                        }
                    ],
                    'Value': latency,
                    'Unit': 'Seconds'
                }
            ]
        )

    except Exception as e:
        print("❌ CloudWatch metric error:", e)

    # -------------------------------------------------
    # 🔵 CLOUDWATCH LOGS
    # -------------------------------------------------

    logger.info(
        f"{request.method} "
        f"{request.path} "
        f"{response.status_code} "
        f"{latency:.4f}s"
    )

    return response

# -------------------------------------------------
# ROUTES
# -------------------------------------------------

@app.route('/')
def index():

    conn = get_db()

    products = conn.execute(
        'SELECT * FROM products'
    ).fetchall()

    conn.close()

    return render_template(
        'index.html',
        products=products
    )

@app.route('/product/<int:product_id>')
def product(product_id):

    conn = get_db()

    product = conn.execute(
        'SELECT * FROM products WHERE id = ?',
        (product_id,)
    ).fetchone()

    conn.close()

    if product is None:
        return "Product not found", 404

    return render_template(
        'product.html',
        product=product
    )

@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):

    cart = session.get('cart', [])

    cart.append(product_id)

    session['cart'] = cart

    flash('Product added!')

    return redirect(
        request.referrer or url_for('index')
    )

@app.route('/cart')
def cart():

    cart_ids = session.get('cart', [])

    cart_items = []

    total = 0

    if cart_ids:

        conn = get_db()

        placeholders = ','.join(
            '?' for _ in cart_ids
        )

        query = f'''
            SELECT * FROM products
            WHERE id IN ({placeholders})
        '''

        products = conn.execute(
            query,
            cart_ids
        ).fetchall()

        from collections import Counter

        counts = Counter(cart_ids)

        product_dict = {
            p['id']: p for p in products
        }

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

    return render_template(
        'cart.html',
        cart_items=cart_items,
        total=total
    )

@app.route('/clear_cart', methods=['POST'])
def clear_cart():

    session['cart'] = []

    flash('Cart cleared!')

    return redirect(url_for('cart'))

@app.route('/checkout', methods=['POST'])
def checkout():

    cart_ids = session.get('cart', [])

    if not cart_ids:
        flash('Your cart is empty!')
        return redirect(url_for('cart'))

    # Calculate total
    conn = get_db()
    placeholders = ','.join('?' for _ in cart_ids)
    query = f'SELECT * FROM products WHERE id IN ({placeholders})'
    products = conn.execute(query, cart_ids).fetchall()
    conn.close()

    from collections import Counter
    counts = Counter(cart_ids)
    product_dict = {p['id']: p for p in products}
    
    total = 0
    for pid, qty in counts.items():
        if pid in product_dict:
            total += product_dict[pid]['price'] * qty

    # Clear cart after checkout
    session['cart'] = []
    session.modified = True

    return redirect(url_for('thank_you', total=f"{total:.2f}"))

@app.route('/thank-you')
def thank_you():
    total = request.args.get('total', '0.00')
    return render_template('thank_you.html', total=total)

# -------------------------------------------------
# 🟢 PROMETHEUS METRICS ENDPOINT
# -------------------------------------------------

@app.route('/metrics')
def metrics():

    return generate_latest(), 200, {
        'Content-Type': CONTENT_TYPE_LATEST
    }

# -------------------------------------------------
# RUN APPLICATION
# -------------------------------------------------

if __name__ == '__main__':

    app.run(
        debug=True,
        host='0.0.0.0',
        port=5000
    )