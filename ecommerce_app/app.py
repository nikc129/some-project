from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os

app = Flask(__name__)
app.secret_key = 'super_secret_premium_key'

DATABASE = 'ecommerce.db'

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
        
        # Demo products
        demo_products = [
            ('Acoustic Noise Cancelling Headphones', 'Premium wireless headphones with industry-leading noise cancellation and immersive audio quality.', 299.99, 'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=500&q=80'),
            ('Mechanical Gaming Keyboard', 'Tactile mechanical switches, customizable RGB backlighting, and an ergonomic aluminum frame.', 149.99, 'https://images.unsplash.com/photo-1595225476474-87563907a212?w=500&q=80'),
            ('4K Action Camera', 'Waterproof, rugged action camera recording in stunning 4K resolution at 60fps.', 199.99, 'https://images.unsplash.com/photo-1526170375885-4d8ecf77b99f?w=500&q=80'),
            ('Smart Fitness Watch', 'Track your health, heart rate, and sleep with this sleek, waterproof smartwatch.', 249.99, 'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=500&q=80'),
            ('Ultra-Slim Power Bank', '10000mAh portable charger with fast-charging capabilities in a sleek, pocket-friendly design.', 49.99, 'https://images.unsplash.com/photo-1609091839311-d5365f9ff1c5?w=500&q=80'),
            ('Minimalist Desk Lamp', 'Adjustable LED desk lamp with touch controls, brightness memory, and a USB charging port.', 79.99, 'https://images.unsplash.com/photo-1507473885765-e6ed057f782c?w=500&q=80')
        ]
        
        cursor.executemany('INSERT INTO products (name, description, price, image_url) VALUES (?, ?, ?, ?)', demo_products)
        conn.commit()
        conn.close()

@app.before_request
def setup():
    init_db()
    if 'cart' not in session:
        session['cart'] = []

@app.route('/')
def index():
    conn = get_db()
    products = conn.execute('SELECT * FROM products').fetchall()
    conn.close()
    return render_template('index.html', products=products)

@app.route('/product/<int:product_id>')
def product(product_id):
    conn = get_db()
    product = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
    conn.close()
    if product is None:
        return "Product not found", 404
    return render_template('product.html', product=product)

@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    cart = session.get('cart', [])
    cart.append(product_id)
    session['cart'] = cart
    flash('Product added to cart!')
    return redirect(request.referrer or url_for('index'))

@app.route('/cart')
def cart():
    cart_item_ids = session.get('cart', [])
    cart_items = []
    total = 0
    if cart_item_ids:
        conn = get_db()
        # Create a comma separated string of question marks for the SQL query
        placeholders = ','.join('?' for _ in cart_item_ids)
        query = f'SELECT * FROM products WHERE id IN ({placeholders})'
        products = conn.execute(query, cart_item_ids).fetchall()
        
        # Count occurrences and calculate total
        from collections import Counter
        item_counts = Counter(cart_item_ids)
        
        # Create a lookup dictionary for products
        product_dict = {p['id']: p for p in products}
        
        # Build cart items with proper quantities
        for product_id, qty in item_counts.items():
            if product_id in product_dict:
                p = product_dict[product_id]
                cart_items.append({
                    'product': p,
                    'quantity': qty,
                    'subtotal': p['price'] * qty
                })
                total += p['price'] * qty
        conn.close()
    
    return render_template('cart.html', cart_items=cart_items, total=total)

@app.route('/clear_cart', methods=['POST'])
def clear_cart():
    session['cart'] = []
    flash('Cart cleared!')
    return redirect(url_for('cart'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
