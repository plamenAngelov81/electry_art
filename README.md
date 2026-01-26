# ElectryArt

**ElectryArt** is a modular, production-ready Django-based e-commerce and manufacturing platform designed to combine **industrial manufacturing, custom CNC/woodcraft products, and digital content** into a single scalable web system.

The project is built with a strong focus on:
- SEO-friendly public storefront
- Clean modular architecture
- Automation and data-driven workflows
- Long-term scalability (multi-shop / SaaS-ready design)

This repository represents an actively developed product, not a demo project.

---

## 🚀 Vision

ElectryArt aims to bridge the gap between **manufacturing, digital design, and e-commerce** by providing a platform where:
- Custom CNC / laser / woodcraft products can be sold online
- Digital and AI-generated content can be distributed
- Quality control and automation systems can later be integrated
- Multiple independent shops can eventually operate under one system (multi-tenant roadmap)

The platform is designed to scale from a **single online store** into a **Shopify-like multi-vendor system** for industrial and creative products.

---

## 🧩 Core Features

### Public Storefront
- SEO-friendly product pages (slug-based URLs)
- Product filtering (price, material, color, availability)
- Sorting (price ↑↓, newest, popularity)
- Wishlist system
- Related products
- JSON-LD Product Schema for Google Rich Results

### User System
- Custom user profiles
- Guest and registered checkout
- Order history and order detail views
- Inquiry and support system

### E-commerce
- Session-based cart system
- Order management
- Order success and tracking pages
- Product categories, materials, and variants

### Site Support
- Terms & Conditions
- Delivery policy
- Returns policy
- Privacy policy
- Contact & support center

### Internationalization
- Django i18n support
- Multi-language-ready templates

---

## 🛠️ Tech Stack

### Backend
- Python 3
- Django
- Django ORM
- PostgreSQL (production-ready)

### Frontend
- HTML5
- CSS3 (custom, no heavy frameworks)
- Vanilla JavaScript (minimal usage, DOM-based where needed)

### DevOps / Tooling
- Git & GitHub
- Feature-based branching workflow
- Environment variable configuration
- Ready for CI/CD integration (GitHub Actions roadmap)

---

## 📂 Project Structure (Simplified)

```
ElectryArt/
│
├── ElectryArt/          # Main Django project settings
├── products/           # Product catalog, filters, SEO, wishlist
├── cart/               # Session cart system
├── orders/            # Orders and order history
├── user_profiles/    # Custom user model and profiles
├── site_support/     # Policies and support pages
├── templates/        # Global templates
├── static/           # CSS, JS, images
├── media/            # User uploads
├── manage.py
└── requirements.txt
```

---

## ⚙️ Installation

### 1. Clone Repository

```bash
git clone https://github.com/YOUR_USERNAME/ElectryArt.git
cd ElectryArt
```

### 2. Create Virtual Environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux / Mac
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Environment Variables

Create a `.env` file in the root directory:

```
SECRET_KEY=your_secret_key
DEBUG=True
DATABASE_NAME=electryart
DATABASE_USER=postgres
DATABASE_PASSWORD=password
DATABASE_HOST=localhost
DATABASE_PORT=5432
```

### 5. Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### 6. Create Superuser

```bash
python manage.py createsuperuser
```

### 7. Run Server

```bash
python manage.py runserver
```

Open:
```
http://127.0.0.1:8000/
```

---

## 🔁 Git Workflow

ElectryArt uses a **feature-branch workflow**:

### Create Feature Branch

```bash
git checkout -b feature/feature-name
```

### Commit Changes

```bash
git add .
git commit -m "Add feature description"
```

### Push Branch

```bash
git push -u origin feature/feature-name
```

### Pull Request

Create a Pull Request on GitHub to merge into `main`.

---

## 🗺️ Roadmap

### Short-Term
- SEO Slugs for all product URLs
- Advanced filters and sorting
- Google Product Schema (JSON-LD)
- UI improvements for cart and wishlist

### Mid-Term
- Product analytics dashboard
- Email notifications (orders, support)
- Role-based access (admin, manager, client)

### Long-Term
- Multi-tenant system (multiple shops)
- Manufacturing automation integration
- Production & quality control data tracking
- API for external systems (ERP / CNC / MES)

---

## 🧠 Philosophy

ElectryArt is built as a **real-world engineering platform**, not just a web shop.

The system is designed to:
- Integrate with manufacturing workflows
- Support automation and data processing
- Scale from small business to industrial-grade platform

---

## 👤 Author

**Plamen Angelov**  
Manufacturing & Software Engineering  

- Python & Django Developer
- CNC & Quality Control Specialist
- Automation & Data Processing Enthusiast

---

## 📄 License

This project is currently under a **private development license**.

Public licensing terms will be defined in future releases.

---

## ⭐ Support

If you find this project interesting or useful, consider giving it a **star** on GitHub — it helps the project grow and reach more developers.

---

> *ElectryArt — Engineering meets creativity.*

