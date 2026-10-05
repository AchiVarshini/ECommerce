# SmartCart

SmartCart is a runnable e-commerce demo with a FastAPI/SQLite backend, a small responsive storefront, seeded catalog and customer behavior data, and persisted purchase and segmentation models.

## Run It

Requires Python 3.11 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.seed --reset
python -m app.analysis
uvicorn app.main:app --reload
```

Open the storefront at `http://127.0.0.1:8000` or the interactive API at `http://127.0.0.1:8000/docs`. FastAPI also seeds an empty database on startup. The explicit seed command rebuilds the demo database, CSVs, and models.

Demo shopper: `customer1@smartcart.com` / `SmartCart123!`  
Demo administrator: `admin@smartcart.com` / `Admin123!`

The browser includes **Sample account** shortcuts on the sign-in form. Registering a new account, browsing and searching the collection, saving products, requesting personalized picks, adding to the bag, checking out, and viewing updated predictions and segments are all connected to live APIs. The administrator view includes revenue/category charts, leading products and customers, segment counts, and low-stock items.

## Libraries

- FastAPI and Uvicorn: HTTP API and development server.
- SQLAlchemy: relational models and SQLite connectivity (`smartcart.db`).
- Pydantic and email-validator: request/response schemas and field validation.
- Pandas and NumPy: synthetic data generation, cleaning, feature engineering, and analysis.
- scikit-learn: Logistic Regression, Decision Tree, Random Forest, K-Means, scaling, and evaluation metrics.
- joblib: serialized model and preprocessing pipelines.
- PyJWT: signed bearer tokens; Python's `hashlib` provides salted password hashing.
- pytest and HTTPX: API integration tests.

## Data And Analysis

The seed script creates these CSVs in `data/` and the matching SQLite records:

- `customers.csv`: 120 customer records.
- `products.csv`: 60 products.
- `orders.csv`: 1,425 order-product rows across 720 distinct orders.
- `customer_activity.csv`: 7,200 customer-product observations with a binary purchase target.

`python -m app.analysis` uses Pandas to inspect missing values and duplicates; normalize dates/numeric fields; drop invalid ages, prices, quantities, and foreign-key references; impute missing ratings from category medians; and write cleaned tables under `data/cleaned/`. It writes the requested EDA answers to `data/eda_summary.json`. The administrator screen visualizes monthly revenue and category sales.

## Machine Learning

Purchase features are age, customer purchase/spend/order-value/visit statistics, product price/rating, product views, cart and wishlist additions, prior product purchases, and time spent. The deterministic seed produces positive and negative outcomes so all three classifiers can be compared on a stratified holdout. Accuracy, precision, recall, F1, confusion matrix, and ROC-AUC are saved for every candidate in `models/purchase_metrics.json`; the highest ROC-AUC model and its fitted preprocessing pipeline are saved in `models/purchase_model.pkl`. On the generated data, Logistic Regression has the best ROC-AUC (0.7949), versus 0.7769 for Random Forest and 0.7527 for Decision Tree.

Customer segments use purchase count, spending, average order value, website visits, and purchase frequency. The scaler and K-Means model compare silhouette scores for k=2 through k=8. Four actionable spend tiers are selected when their score is within 0.01 of the highest-scoring k; this keeps useful At-Risk, Occasional, Regular, and Premium groups while retaining near-best separation. The selected k and scores are in `models/segmentation_metrics.json`, and the fitted model is `models/customer_segment.pkl`.

For the current sample, Electronics has the most revenue ($87,896.69); Hiking Socks leads product revenue ($17,084.61); the mean order value is $621.68; Google Pay is the most-used payment method (161 orders); Boston has the most seeded customers (16); and 99.17% of seeded customers have repeat orders. The full ranked lists and monthly revenue are in `data/eda_summary.json` and the admin analytics APIs.

The recommendations combine purchase-model probability, category affinity from order history, product rating, and catalog popularity, with a downweight for products already purchased.

## API Map

- Authentication: `POST /register`, `POST /login`.
- Customers: CRUD at `/customers`; orders at `/customers/{customer_id}/orders`; account metrics and recommendations at `/customer-dashboard/{customer_id}`.
- Products: CRUD at `/products`, with `search`, `category`, and `sort` query parameters; product views and wishlist activity are recorded too.
- Cart and checkout: `/cart` endpoints and `POST /orders` reserve stock, create order items, update customer behavior, and clear the cart.
- Personalized ML: `POST /predict-purchase`, `GET /recommendations/{customer_id}`, `GET /customer-segment/{customer_id}`.
- Administrator analytics: `/admin/sales-summary`, `/admin/top-products`, `/admin/top-customers`, `/admin/category-sales`, `/admin/customer-segments`, `/admin/low-stock-products`, `/admin/eda`, `/admin/data-quality`.

Protected operations use bearer JWTs. Administrator analytics and product writes require the admin role. Customer reads, cart actions, orders, predictions, and recommendations are limited to that customer (or an administrator). API errors use appropriate 4xx/5xx status codes for missing records, invalid data, authorization, stock, empty carts, and unavailable models.

## Configuration And Tests

Set `DATABASE_URL` to use another SQLAlchemy-supported database. Set `JWT_SECRET` to a long random value before deployment; the checked-in fallback is for local development only. Demo credentials are deliberately simple and must not be reused outside this sample.

```bash
python -m pytest -q
```