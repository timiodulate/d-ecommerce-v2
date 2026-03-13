# E1 Clothing

A full-featured e-commerce clothing store built with React, FastAPI, and MongoDB.

Minimalist luxury design. Curated essentials for the modern wardrobe.

![E1 Clothing](https://images.unsplash.com/photo-1652281846249-f81974eba5b4?q=80&w=1200&auto=format&fit=crop)

---

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Architecture](#architecture)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [API Reference](#api-reference)
- [Project Structure](#project-structure)
- [Seed Data](#seed-data)
- [Screenshots](#screenshots)
- [Roadmap](#roadmap)
- [License](#license)

---

## Features

### Storefront

- **Product Catalog** — Browse 12+ curated clothing items across Men, Women, and Accessories
- **Filtering & Sorting** — Filter by category, search by name/description, sort by price or name
- **Product Detail** — Size selector, color selector, quantity controls, stock indicators
- **Shopping Cart** — Client-side cart persisted to localStorage, real-time total calculation
- **Stripe Checkout** — Secure payment processing with server-side price validation
- **Order Tracking** — View order history with status updates (pending, paid, shipped, delivered)

### Authentication

- **JWT Auth** — Register/login with email and password
- **Token Persistence** — Auto-login on return visits via localStorage
- **Role-Based Access** — User and Admin roles with protected routes

### Admin Dashboard

- **Overview** — Revenue, order count, product count, customer count at a glance
- **Product Management** — Full CRUD (create, read, update, delete) via modal forms
- **Order Management** — View all orders, update statuses (pending → paid → shipped → delivered)

---

## Tech Stack

| Layer      | Technology                                          |
| ---------- | --------------------------------------------------- |
| Frontend   | React 19, Tailwind CSS 3, shadcn/ui, React Router 7 |
| Backend    | FastAPI, Pydantic, Motor (async MongoDB driver)     |
| Database   | MongoDB                                             |
| Auth       | JWT (PyJWT + bcrypt)                                |
| Payments   | Stripe (via emergentintegrations library)           |
| Typography | Playfair Display (headings), Inter (body)           |
| Icons      | Lucide React                                        |

---

## Architecture

```
┌─────────────────────────────────────────────┐
│                  Browser                     │
│  React + Tailwind + shadcn/ui               │
│  ├── AuthContext (JWT in localStorage)       │
│  └── CartContext (cart in localStorage)      │
└──────────────────┬──────────────────────────┘
                   │ HTTP (JSON)
                   ▼
┌─────────────────────────────────────────────┐
│               FastAPI Backend                │
│  ├── /api/auth/*      (JWT auth)            │
│  ├── /api/products/*  (catalog CRUD)        │
│  ├── /api/payments/*  (Stripe checkout)     │
│  ├── /api/orders/*    (user orders)         │
│  ├── /api/admin/*     (admin dashboard)     │
│  └── /api/webhook/*   (Stripe webhooks)     │
└──────────────────┬──────────────────────────┘
                   │
          ┌────────┴────────┐
          ▼                 ▼
   ┌────────────┐    ┌───────────┐
   │  MongoDB   │    │  Stripe   │
   │            │    │  API      │
   │ Collections│    │           │
   │ ├─ users   │    │ Checkout  │
   │ ├─ products│    │ Sessions  │
   │ ├─ orders  │    └───────────┘
   │ └─ payment_│
   │  transactions│
   └────────────┘
```

### Data Flow — Checkout

1. User adds items to cart (stored in localStorage)
2. User fills shipping form on `/checkout`
3. Frontend sends cart item IDs + shipping address to backend
4. **Backend looks up actual prices from database** (prevents price manipulation)
5. Backend creates an Order document (status: `pending`)
6. Backend creates a Stripe Checkout Session
7. Backend creates a `payment_transactions` record (status: `initiated`)
8. Frontend redirects user to Stripe's hosted checkout page
9. After payment, Stripe redirects to `/payment/success?session_id=...`
10. Frontend polls `GET /api/payments/status/:session_id`
11. Backend verifies payment with Stripe, updates order status to `paid`
12. Cart is cleared on success

---

## Getting Started

### Prerequisites

- **Node.js** >= 18 and **Yarn**
- **Python** >= 3.11
- **MongoDB** running locally on port 27017
- **Stripe test key** (or use the provided test key)

### 1. Clone and install

```bash
git clone <your-repo-url>
cd e1-clothing
```

### 2. Backend setup

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create `backend/.env`:

```env
MONGO_URL=mongodb://localhost:27017
DB_NAME=e1_clothing
CORS_ORIGINS=http://localhost:3000
STRIPE_API_KEY=sk_test_your_stripe_key_here
JWT_SECRET=your-secret-key-change-in-production
```

Start the backend:

```bash
uvicorn server:app --reload --port 8001
```

The server will automatically seed 12 products and an admin user on first startup.

### 3. Frontend setup

```bash
cd frontend
yarn install
```

Create `frontend/.env`:

```env
REACT_APP_BACKEND_URL=http://localhost:8001
```

Start the frontend:

```bash
yarn start
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

### 4. Admin access

```
Email:    admin@e1clothing.com
Password: admin123
```

Login and navigate to `/admin` to access the dashboard.

---

## Environment Variables

### Backend (`backend/.env`)

| Variable         | Description                       | Example                     |
| ---------------- | --------------------------------- | --------------------------- |
| `MONGO_URL`      | MongoDB connection string         | `mongodb://localhost:27017` |
| `DB_NAME`        | Database name                     | `e1_clothing`               |
| `CORS_ORIGINS`   | Allowed origins (comma-separated) | `http://localhost:3000`     |
| `STRIPE_API_KEY` | Stripe secret key (test or live)  | `sk_test_...`               |
| `JWT_SECRET`     | Secret key for signing JWT tokens | `your-secret-key`           |

### Frontend (`frontend/.env`)

| Variable                | Description          | Example                 |
| ----------------------- | -------------------- | ----------------------- |
| `REACT_APP_BACKEND_URL` | Backend API base URL | `http://localhost:8001` |

---

## API Reference

All endpoints are prefixed with `/api`.

### Auth

| Method | Endpoint             | Auth   | Description                 |
| ------ | -------------------- | ------ | --------------------------- |
| POST   | `/api/auth/register` | Public | Create a new account        |
| POST   | `/api/auth/login`    | Public | Login and receive JWT token |
| GET    | `/api/auth/me`       | Bearer | Get current user profile    |

### Products

| Method | Endpoint            | Auth   | Description                                                                                |
| ------ | ------------------- | ------ | ------------------------------------------------------------------------------------------ |
| GET    | `/api/products`     | Public | List products (query: category, search, sort, min_price, max_price, featured, limit, skip) |
| GET    | `/api/products/:id` | Public | Get single product by ID                                                                   |
| POST   | `/api/products`     | Admin  | Create a new product                                                                       |
| PUT    | `/api/products/:id` | Admin  | Update an existing product                                                                 |
| DELETE | `/api/products/:id` | Admin  | Delete a product                                                                           |

### Payments

| Method | Endpoint                           | Auth   | Description                    |
| ------ | ---------------------------------- | ------ | ------------------------------ |
| POST   | `/api/payments/create-checkout`    | Bearer | Create Stripe checkout session |
| GET    | `/api/payments/status/:session_id` | Bearer | Poll payment status            |
| POST   | `/api/webhook/stripe`              | Public | Stripe webhook handler         |

### Orders

| Method | Endpoint          | Auth   | Description                |
| ------ | ----------------- | ------ | -------------------------- |
| GET    | `/api/orders`     | Bearer | Get current user's orders  |
| GET    | `/api/orders/:id` | Bearer | Get specific order details |

### Admin

| Method | Endpoint                       | Auth  | Description                   |
| ------ | ------------------------------ | ----- | ----------------------------- |
| GET    | `/api/admin/stats`             | Admin | Dashboard statistics          |
| GET    | `/api/admin/orders`            | Admin | All orders with customer info |
| PUT    | `/api/admin/orders/:id/status` | Admin | Update order status           |

---

## Project Structure

```
e1-clothing/
├── backend/
│   ├── .env                          # Environment variables
│   ├── requirements.txt              # Python dependencies
│   └── server.py                     # FastAPI application (all routes, models, seed data)
│
├── frontend/
│   ├── .env                          # Environment variables
│   ├── package.json                  # Node dependencies
│   ├── tailwind.config.js            # Tailwind configuration with design tokens
│   ├── postcss.config.js             # PostCSS config
│   ├── public/
│   │   └── index.html
│   └── src/
│       ├── index.js                  # React entry point
│       ├── index.css                 # Design system (CSS variables, fonts, Tailwind)
│       ├── App.js                    # Routes and providers
│       ├── App.css                   # Animations (marquee, fade-in)
│       │
│       ├── context/
│       │   ├── AuthContext.js         # JWT auth state management
│       │   └── CartContext.js         # Cart state with localStorage
│       │
│       ├── components/
│       │   ├── ui/                   # shadcn/ui components (button, card, dialog, etc.)
│       │   ├── layout/
│       │   │   ├── Navbar.js         # Sticky nav with glassmorphism
│       │   │   └── Footer.js         # Dark footer with link grid
│       │   └── ProductCard.js        # Reusable product card component
│       │
│       └── pages/
│           ├── Home.js               # Hero, marquee, categories, featured, newsletter
│           ├── Shop.js               # Product grid with sidebar filters
│           ├── ProductDetail.js      # Split layout with size/color selection
│           ├── Cart.js               # Cart items and order summary
│           ├── Checkout.js           # Shipping form + Stripe redirect
│           ├── Login.js              # Sign in form
│           ├── Register.js           # Create account form
│           ├── Profile.js            # User info + order history
│           ├── AdminDashboard.js     # Stats, product CRUD, order management
│           └── PaymentSuccess.js     # Payment confirmation with polling
│
├── .gitignore
└── README.md
```

---

## Seed Data

On first startup, the backend seeds the database with:

### Admin User

| Field    | Value                  |
| -------- | ---------------------- |
| Email    | `admin@e1clothing.com` |
| Password | `admin123`             |
| Role     | `admin`                |

### Products (12 items)

| Product                | Category    | Price   | Featured |
| ---------------------- | ----------- | ------- | -------- |
| Essential Crew Tee     | Men         | $45.00  | Yes      |
| Tailored Chinos        | Men         | $89.00  | No       |
| Cashmere Blend Sweater | Men         | $165.00 | Yes      |
| Classic Oxford Shirt   | Men         | $75.00  | No       |
| Linen Summer Shirt     | Men         | $85.00  | No       |
| Silk Blend Blouse      | Women       | $120.00 | Yes      |
| Wide Leg Trousers      | Women       | $95.00  | No       |
| Midi Wrap Dress        | Women       | $145.00 | Yes      |
| Oversized Blazer       | Women       | $195.00 | No       |
| Pleated Midi Skirt     | Women       | $110.00 | Yes      |
| Leather Belt           | Accessories | $55.00  | No       |
| Merino Wool Scarf      | Accessories | $65.00  | No       |

Each product includes multiple sizes, color variants (with hex codes), and Unsplash product imagery.

---

## Design System

| Element       | Value                                                  |
| ------------- | ------------------------------------------------------ |
| Headings      | Playfair Display (serif, 400/500/600)                  |
| Body          | Inter (sans-serif, 300/400/500/600)                    |
| Palette       | Stone 900 `#1C1917` / Stone 50 `#FAFAF9` / White       |
| Radius        | `0` (sharp edges throughout)                           |
| Spacing       | Generous — 2-3x more than default                      |
| Navbar        | Sticky, glassmorphism (`backdrop-blur-md bg-white/80`) |
| Admin Sidebar | Dark (`bg-stone-900 text-stone-300`)                   |
| Cards         | No shadow, subtle borders (`border-stone-200`)         |
| Buttons       | Uppercase, tracked, no radius                          |

---

## MongoDB Collections

| Collection             | Purpose                                                                   |
| ---------------------- | ------------------------------------------------------------------------- |
| `users`                | User accounts (id, email, password_hash, name, role)                      |
| `products`             | Product catalog (id, name, price, category, sizes, colors, images, stock) |
| `orders`               | Customer orders (id, user_id, items, total, status, shipping_address)     |
| `payment_transactions` | Stripe payment records (session_id, amount, status, payment_status)       |

---

## Roadmap

- [ ] Product reviews and ratings
- [ ] Wishlist / favorites
- [ ] Email order confirmations (SendGrid or Resend)
- [ ] Product image upload in admin
- [ ] Coupon / discount code system
- [ ] Related products suggestions
- [ ] Abandoned cart email recovery
- [ ] Social login (Google OAuth)
- [ ] Advanced search with autocomplete
- [ ] Infinite scroll pagination

---

## License

MIT
