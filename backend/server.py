from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Header
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
import uuid
from datetime import datetime, timezone, timedelta
import jwt
import bcrypt

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

STRIPE_API_KEY = os.environ.get('STRIPE_API_KEY')
JWT_SECRET = os.environ.get('JWT_SECRET')
JWT_ALGORITHM = 'HS256'

app = FastAPI()
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ═══════════════════ MODELS ═══════════════════

class UserRegister(BaseModel):
    email: str
    password: str
    name: str

class UserLogin(BaseModel):
    email: str
    password: str

class ProductCreate(BaseModel):
    name: str
    description: str = ""
    price: float
    category: str
    subcategory: str = ""
    sizes: List[str] = []
    colors: List[Dict[str, str]] = []
    images: List[str] = []
    featured: bool = False
    stock: int = 0

class CheckoutCartItem(BaseModel):
    product_id: str
    quantity: int
    size: str
    color: str

class ShippingAddress(BaseModel):
    name: str
    address: str
    city: str
    state: str
    zip_code: str
    country: str

class CheckoutRequest(BaseModel):
    items: List[CheckoutCartItem]
    shipping_address: ShippingAddress
    origin_url: str

class OrderStatusUpdate(BaseModel):
    status: str

# ═══════════════════ AUTH HELPERS ═══════════════════

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def create_token(user_id: str, role: str) -> str:
    payload = {
        'user_id': user_id,
        'role': role,
        'exp': datetime.now(timezone.utc) + timedelta(hours=24)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail='Not authenticated')
    token = authorization.split(' ')[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user = await db.users.find_one({'id': payload['user_id']}, {'_id': 0})
        if not user:
            raise HTTPException(status_code=401, detail='User not found')
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail='Token expired')
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail='Invalid token')

async def get_admin_user(user=Depends(get_current_user)):
    if user.get('role') != 'admin':
        raise HTTPException(status_code=403, detail='Admin access required')
    return user

# ═══════════════════ AUTH ROUTES ═══════════════════

@api_router.post("/auth/register")
async def register(data: UserRegister):
    existing = await db.users.find_one({'email': data.email})
    if existing:
        raise HTTPException(status_code=400, detail='Email already registered')
    user_id = str(uuid.uuid4())
    user = {
        'id': user_id,
        'email': data.email,
        'password_hash': hash_password(data.password),
        'name': data.name,
        'role': 'user',
        'created_at': datetime.now(timezone.utc).isoformat()
    }
    await db.users.insert_one(user)
    token = create_token(user_id, 'user')
    return {'token': token, 'user': {'id': user_id, 'email': data.email, 'name': data.name, 'role': 'user'}}

@api_router.post("/auth/login")
async def login(data: UserLogin):
    user = await db.users.find_one({'email': data.email}, {'_id': 0})
    if not user or not verify_password(data.password, user['password_hash']):
        raise HTTPException(status_code=401, detail='Invalid credentials')
    token = create_token(user['id'], user['role'])
    return {'token': token, 'user': {'id': user['id'], 'email': user['email'], 'name': user['name'], 'role': user['role']}}

@api_router.get("/auth/me")
async def get_me(user=Depends(get_current_user)):
    return {'id': user['id'], 'email': user['email'], 'name': user['name'], 'role': user['role']}

# ═══════════════════ PRODUCT ROUTES ═══════════════════

@api_router.get("/products")
async def get_products(
    category: Optional[str] = None,
    search: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    featured: Optional[bool] = None,
    sort: Optional[str] = None,
    limit: int = 50,
    skip: int = 0
):
    query = {}
    if category:
        query['category'] = category
    if search:
        query['$or'] = [
            {'name': {'$regex': search, '$options': 'i'}},
            {'description': {'$regex': search, '$options': 'i'}}
        ]
    if min_price is not None or max_price is not None:
        price_q = {}
        if min_price is not None:
            price_q['$gte'] = min_price
        if max_price is not None:
            price_q['$lte'] = max_price
        query['price'] = price_q
    if featured is not None:
        query['featured'] = featured

    sort_field = [('created_at', -1)]
    if sort == 'price_asc':
        sort_field = [('price', 1)]
    elif sort == 'price_desc':
        sort_field = [('price', -1)]
    elif sort == 'name':
        sort_field = [('name', 1)]

    products = await db.products.find(query, {'_id': 0}).sort(sort_field).skip(skip).limit(limit).to_list(limit)
    total = await db.products.count_documents(query)
    return {'products': products, 'total': total}

@api_router.get("/products/{product_id}")
async def get_product(product_id: str):
    product = await db.products.find_one({'id': product_id}, {'_id': 0})
    if not product:
        raise HTTPException(status_code=404, detail='Product not found')
    return product

@api_router.post("/products")
async def create_product(data: ProductCreate, user=Depends(get_admin_user)):
    product = {
        'id': str(uuid.uuid4()),
        **data.model_dump(),
        'created_at': datetime.now(timezone.utc).isoformat()
    }
    await db.products.insert_one(product)
    created = await db.products.find_one({'id': product['id']}, {'_id': 0})
    return created

@api_router.put("/products/{product_id}")
async def update_product(product_id: str, data: ProductCreate, user=Depends(get_admin_user)):
    result = await db.products.update_one({'id': product_id}, {'$set': data.model_dump()})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail='Product not found')
    updated = await db.products.find_one({'id': product_id}, {'_id': 0})
    return updated

@api_router.delete("/products/{product_id}")
async def delete_product(product_id: str, user=Depends(get_admin_user)):
    result = await db.products.delete_one({'id': product_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail='Product not found')
    return {'message': 'Product deleted'}

# ═══════════════════ PAYMENT ROUTES ═══════════════════

@api_router.post("/payments/create-checkout")
async def create_checkout(data: CheckoutRequest, request: Request, user=Depends(get_current_user)):
    from emergentintegrations.payments.stripe.checkout import StripeCheckout, CheckoutSessionRequest

    if not data.items:
        raise HTTPException(status_code=400, detail='Cart is empty')

    total = 0.0
    order_items = []
    for item in data.items:
        product = await db.products.find_one({'id': item.product_id}, {'_id': 0})
        if not product:
            raise HTTPException(status_code=400, detail=f'Product {item.product_id} not found')
        total += product['price'] * item.quantity
        order_items.append({
            'product_id': item.product_id,
            'name': product['name'],
            'price': product['price'],
            'quantity': item.quantity,
            'size': item.size,
            'color': item.color,
            'image': product['images'][0] if product.get('images') else ''
        })

    if total <= 0:
        raise HTTPException(status_code=400, detail='Invalid cart total')

    order_id = str(uuid.uuid4())
    order = {
        'id': order_id,
        'user_id': user['id'],
        'items': order_items,
        'total': round(total, 2),
        'status': 'pending',
        'shipping_address': data.shipping_address.model_dump(),
        'payment_session_id': None,
        'created_at': datetime.now(timezone.utc).isoformat()
    }
    await db.orders.insert_one(order)

    origin_url = data.origin_url.rstrip('/')
    success_url = f"{origin_url}/payment/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{origin_url}/cart"

    host_url = str(request.base_url)
    webhook_url = f"{host_url}api/webhook/stripe"

    stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)

    checkout_request = CheckoutSessionRequest(
        amount=round(total, 2),
        currency='usd',
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={'order_id': order_id, 'user_id': user['id']}
    )

    session = await stripe_checkout.create_checkout_session(checkout_request)

    await db.orders.update_one({'id': order_id}, {'$set': {'payment_session_id': session.session_id}})

    payment_tx = {
        'id': str(uuid.uuid4()),
        'session_id': session.session_id,
        'user_id': user['id'],
        'order_id': order_id,
        'amount': round(total, 2),
        'currency': 'usd',
        'status': 'initiated',
        'payment_status': 'pending',
        'metadata': {'order_id': order_id, 'user_id': user['id']},
        'created_at': datetime.now(timezone.utc).isoformat()
    }
    await db.payment_transactions.insert_one(payment_tx)

    return {'url': session.url, 'session_id': session.session_id, 'order_id': order_id}

@api_router.get("/payments/status/{session_id}")
async def get_payment_status(session_id: str, request: Request, user=Depends(get_current_user)):
    from emergentintegrations.payments.stripe.checkout import StripeCheckout

    host_url = str(request.base_url)
    webhook_url = f"{host_url}api/webhook/stripe"
    stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)

    status = await stripe_checkout.get_checkout_status(session_id)

    tx = await db.payment_transactions.find_one({'session_id': session_id}, {'_id': 0})
    if tx and tx.get('payment_status') != 'paid':
        new_status = status.payment_status
        await db.payment_transactions.update_one(
            {'session_id': session_id},
            {'$set': {'status': status.status, 'payment_status': new_status}}
        )
        if new_status == 'paid':
            await db.orders.update_one({'id': tx['order_id']}, {'$set': {'status': 'paid'}})

    return {
        'status': status.status,
        'payment_status': status.payment_status,
        'amount_total': status.amount_total,
        'currency': status.currency,
        'order_id': tx['order_id'] if tx else None
    }

@api_router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    from emergentintegrations.payments.stripe.checkout import StripeCheckout

    body = await request.body()
    signature = request.headers.get("Stripe-Signature")

    host_url = str(request.base_url)
    webhook_url = f"{host_url}api/webhook/stripe"
    stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)

    try:
        webhook_response = await stripe_checkout.handle_webhook(body, signature)
        if webhook_response.payment_status == 'paid':
            session_id = webhook_response.session_id
            tx = await db.payment_transactions.find_one({'session_id': session_id}, {'_id': 0})
            if tx and tx.get('payment_status') != 'paid':
                await db.payment_transactions.update_one(
                    {'session_id': session_id},
                    {'$set': {'status': 'complete', 'payment_status': 'paid'}}
                )
                await db.orders.update_one({'id': tx['order_id']}, {'$set': {'status': 'paid'}})
        return {'status': 'ok'}
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

# ═══════════════════ ORDER ROUTES ═══════════════════

@api_router.get("/orders")
async def get_user_orders(user=Depends(get_current_user)):
    orders = await db.orders.find({'user_id': user['id']}, {'_id': 0}).sort('created_at', -1).to_list(100)
    return orders

@api_router.get("/orders/{order_id}")
async def get_order(order_id: str, user=Depends(get_current_user)):
    order = await db.orders.find_one({'id': order_id, 'user_id': user['id']}, {'_id': 0})
    if not order:
        raise HTTPException(status_code=404, detail='Order not found')
    return order

# ═══════════════════ ADMIN ROUTES ═══════════════════

@api_router.get("/admin/stats")
async def get_admin_stats(user=Depends(get_admin_user)):
    total_products = await db.products.count_documents({})
    total_orders = await db.orders.count_documents({})
    total_users = await db.users.count_documents({})

    paid_orders = await db.orders.find({'status': {'$in': ['paid', 'shipped', 'delivered']}}, {'_id': 0, 'total': 1}).to_list(10000)
    total_revenue = sum(o.get('total', 0) for o in paid_orders)

    recent_orders = await db.orders.find({}, {'_id': 0}).sort('created_at', -1).limit(10).to_list(10)
    for order in recent_orders:
        user_info = await db.users.find_one({'id': order.get('user_id')}, {'_id': 0, 'name': 1, 'email': 1})
        if user_info:
            order['user_name'] = user_info.get('name', '')
            order['user_email'] = user_info.get('email', '')

    return {
        'total_products': total_products,
        'total_orders': total_orders,
        'total_users': total_users,
        'total_revenue': round(total_revenue, 2),
        'recent_orders': recent_orders
    }

@api_router.get("/admin/orders")
async def get_all_orders(user=Depends(get_admin_user)):
    orders = await db.orders.find({}, {'_id': 0}).sort('created_at', -1).to_list(1000)
    for order in orders:
        user_info = await db.users.find_one({'id': order.get('user_id')}, {'_id': 0, 'name': 1, 'email': 1})
        if user_info:
            order['user_name'] = user_info.get('name', '')
            order['user_email'] = user_info.get('email', '')
    return orders

@api_router.put("/admin/orders/{order_id}/status")
async def update_order_status(order_id: str, data: OrderStatusUpdate, user=Depends(get_admin_user)):
    result = await db.orders.update_one({'id': order_id}, {'$set': {'status': data.status}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail='Order not found')
    return {'message': 'Order status updated'}

# ═══════════════════ SEED DATA ═══════════════════

SEED_PRODUCTS = [
    {
        'name': 'Essential Crew Tee',
        'description': 'A perfectly weighted cotton crew neck tee. Relaxed fit with premium hand-feel. The foundation of every wardrobe, crafted from 100% organic cotton.',
        'price': 45.00,
        'category': 'men',
        'subcategory': 'tops',
        'sizes': ['XS', 'S', 'M', 'L', 'XL'],
        'colors': [{'name': 'White', 'hex': '#FFFFFF'}, {'name': 'Black', 'hex': '#1C1917'}, {'name': 'Stone', 'hex': '#A8A29E'}],
        'images': ['https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=800&auto=format&fit=crop'],
        'featured': True,
        'stock': 120
    },
    {
        'name': 'Tailored Chinos',
        'description': 'Refined slim-fit chinos crafted from organic stretch cotton twill. Versatile enough to dress up or down for any occasion.',
        'price': 89.00,
        'category': 'men',
        'subcategory': 'bottoms',
        'sizes': ['28', '30', '32', '34', '36'],
        'colors': [{'name': 'Khaki', 'hex': '#C4B5A0'}, {'name': 'Navy', 'hex': '#1E293B'}, {'name': 'Olive', 'hex': '#4A5240'}],
        'images': ['https://images.unsplash.com/photo-1473966968600-fa801b869a1a?w=800&auto=format&fit=crop'],
        'featured': False,
        'stock': 85
    },
    {
        'name': 'Cashmere Blend Sweater',
        'description': 'Luxurious cashmere-wool blend knit with a relaxed silhouette. Perfectly weighted for transitional seasons.',
        'price': 165.00,
        'category': 'men',
        'subcategory': 'tops',
        'sizes': ['S', 'M', 'L', 'XL'],
        'colors': [{'name': 'Oatmeal', 'hex': '#D4C5A9'}, {'name': 'Charcoal', 'hex': '#44403C'}],
        'images': ['https://images.unsplash.com/photo-1576566588028-4147f3842f27?w=800&auto=format&fit=crop'],
        'featured': True,
        'stock': 45
    },
    {
        'name': 'Classic Oxford Shirt',
        'description': 'A timeless button-down Oxford shirt in premium cotton. Clean lines, impeccable fit, enduring style.',
        'price': 75.00,
        'category': 'men',
        'subcategory': 'tops',
        'sizes': ['S', 'M', 'L', 'XL'],
        'colors': [{'name': 'White', 'hex': '#FFFFFF'}, {'name': 'Light Blue', 'hex': '#BFDBFE'}],
        'images': ['https://images.unsplash.com/photo-1596755094514-f87e34085b2c?w=800&auto=format&fit=crop'],
        'featured': False,
        'stock': 70
    },
    {
        'name': 'Silk Blend Blouse',
        'description': 'Fluid silk-blend blouse with a relaxed drape. Effortlessly elegant for day-to-evening transitions.',
        'price': 120.00,
        'category': 'women',
        'subcategory': 'tops',
        'sizes': ['XS', 'S', 'M', 'L'],
        'colors': [{'name': 'Ivory', 'hex': '#FEFCE8'}, {'name': 'Black', 'hex': '#1C1917'}],
        'images': ['https://images.unsplash.com/photo-1551488831-00ddcb6c6bd3?w=800&auto=format&fit=crop'],
        'featured': True,
        'stock': 55
    },
    {
        'name': 'Wide Leg Trousers',
        'description': 'High-waisted wide leg trousers in fluid crepe. A modern silhouette that moves with grace.',
        'price': 95.00,
        'category': 'women',
        'subcategory': 'bottoms',
        'sizes': ['XS', 'S', 'M', 'L', 'XL'],
        'colors': [{'name': 'Black', 'hex': '#1C1917'}, {'name': 'Sand', 'hex': '#D6CFC7'}],
        'images': ['https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=800&auto=format&fit=crop'],
        'featured': False,
        'stock': 60
    },
    {
        'name': 'Midi Wrap Dress',
        'description': 'A universally flattering wrap dress in flowing viscose. Cinched waist with a graceful midi hem.',
        'price': 145.00,
        'category': 'women',
        'subcategory': 'dresses',
        'sizes': ['XS', 'S', 'M', 'L'],
        'colors': [{'name': 'Terracotta', 'hex': '#C2724F'}, {'name': 'Forest', 'hex': '#365314'}],
        'images': ['https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=800&auto=format&fit=crop'],
        'featured': True,
        'stock': 40
    },
    {
        'name': 'Oversized Blazer',
        'description': 'Architecturally cut oversized blazer in structured wool blend. Sharp shoulders, relaxed body.',
        'price': 195.00,
        'category': 'women',
        'subcategory': 'outerwear',
        'sizes': ['XS', 'S', 'M', 'L'],
        'colors': [{'name': 'Black', 'hex': '#1C1917'}, {'name': 'Camel', 'hex': '#A68B6B'}],
        'images': ['https://images.unsplash.com/photo-1591047139829-d91aecb6caea?w=800&auto=format&fit=crop'],
        'featured': False,
        'stock': 35
    },
    {
        'name': 'Leather Belt',
        'description': 'Full-grain Italian leather belt with brushed brass buckle. A refined essential that ages beautifully.',
        'price': 55.00,
        'category': 'accessories',
        'subcategory': 'belts',
        'sizes': ['S', 'M', 'L'],
        'colors': [{'name': 'Tan', 'hex': '#92704F'}, {'name': 'Black', 'hex': '#1C1917'}],
        'images': ['https://images.unsplash.com/photo-1553062407-98eeb64c6a62?w=800&auto=format&fit=crop'],
        'featured': False,
        'stock': 100
    },
    {
        'name': 'Merino Wool Scarf',
        'description': 'Ultra-soft merino wool scarf with delicate fringe edges. Lightweight warmth in timeless elegance.',
        'price': 65.00,
        'category': 'accessories',
        'subcategory': 'scarves',
        'sizes': ['One Size'],
        'colors': [{'name': 'Grey', 'hex': '#78716C'}, {'name': 'Cream', 'hex': '#F5F0EB'}],
        'images': ['https://images.unsplash.com/photo-1520903920243-00d872a2d1c9?w=800&auto=format&fit=crop'],
        'featured': False,
        'stock': 90
    },
    {
        'name': 'Linen Summer Shirt',
        'description': 'Breathable pure linen shirt with a relaxed camp collar. Made for warm days and easy living.',
        'price': 85.00,
        'category': 'men',
        'subcategory': 'tops',
        'sizes': ['S', 'M', 'L', 'XL'],
        'colors': [{'name': 'White', 'hex': '#FFFFFF'}, {'name': 'Sky', 'hex': '#7DD3FC'}],
        'images': ['https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=800&auto=format&fit=crop'],
        'featured': False,
        'stock': 65
    },
    {
        'name': 'Pleated Midi Skirt',
        'description': 'Flowing pleated midi skirt in premium satin. Movement and shimmer in every step.',
        'price': 110.00,
        'category': 'women',
        'subcategory': 'bottoms',
        'sizes': ['XS', 'S', 'M', 'L'],
        'colors': [{'name': 'Champagne', 'hex': '#E8D5B7'}, {'name': 'Black', 'hex': '#1C1917'}],
        'images': ['https://images.unsplash.com/photo-1583496661160-fb5886a0aaaa?w=800&auto=format&fit=crop'],
        'featured': True,
        'stock': 50
    }
]

@app.on_event("startup")
async def seed_data():
    product_count = await db.products.count_documents({})
    if product_count == 0:
        logger.info("Seeding products...")
        for p in SEED_PRODUCTS:
            p['id'] = str(uuid.uuid4())
            p['created_at'] = datetime.now(timezone.utc).isoformat()
            await db.products.insert_one(p)
        logger.info(f"Seeded {len(SEED_PRODUCTS)} products")

    admin = await db.users.find_one({'email': 'admin@e1clothing.com'})
    if not admin:
        logger.info("Seeding admin user...")
        admin_user = {
            'id': str(uuid.uuid4()),
            'email': 'admin@e1clothing.com',
            'password_hash': hash_password('admin123'),
            'name': 'Admin',
            'role': 'admin',
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        await db.users.insert_one(admin_user)
        logger.info("Admin user created: admin@e1clothing.com / admin123")

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
