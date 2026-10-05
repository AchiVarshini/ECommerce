import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score, silhouette_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier


ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = ROOT / "models"
PURCHASE_MODEL = MODEL_DIR / "purchase_model.pkl"
SEGMENT_MODEL = MODEL_DIR / "customer_segment.pkl"
FEATURES = [
    "customer_age", "total_purchases", "total_spending", "average_order_value",
    "website_visits", "product_price", "product_rating", "product_views",
    "cart_additions", "wishlist_additions", "previous_purchases", "time_spent",
]
SEGMENT_FEATURES = ["total_purchases", "total_spending", "average_order_value", "website_visits", "purchase_frequency"]


def train_purchase_model(activity: pd.DataFrame) -> dict:
    if activity.empty or activity["purchased"].nunique() < 2:
        raise ValueError("Training activity must include both purchase outcomes")
    x = activity[FEATURES].astype(float)
    y = activity["purchased"].astype(int)
    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=0.25, random_state=42, stratify=y
    )
    candidates = {
        "Logistic Regression": make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42)),
        "Decision Tree": DecisionTreeClassifier(max_depth=8, min_samples_leaf=4, class_weight="balanced", random_state=42),
        "Random Forest": RandomForestClassifier(n_estimators=160, min_samples_leaf=2, class_weight="balanced", random_state=42, n_jobs=-1),
    }
    results = {}
    best_name, best_model, best_auc = None, None, -1
    for name, model in candidates.items():
        model.fit(x_train, y_train)
        probability = model.predict_proba(x_test)[:, 1]
        prediction = (probability >= 0.5).astype(int)
        auc = float(roc_auc_score(y_test, probability))
        results[name] = {
            "accuracy": round(float(accuracy_score(y_test, prediction)), 4),
            "precision": round(float(precision_score(y_test, prediction, zero_division=0)), 4),
            "recall": round(float(recall_score(y_test, prediction, zero_division=0)), 4),
            "f1": round(float(f1_score(y_test, prediction, zero_division=0)), 4),
            "roc_auc": round(auc, 4),
            "confusion_matrix": confusion_matrix(y_test, prediction).tolist(),
        }
        if auc > best_auc:
            best_name, best_model, best_auc = name, model, auc
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": best_model, "features": FEATURES, "name": best_name, "metrics": results}, PURCHASE_MODEL)
    (MODEL_DIR / "purchase_metrics.json").write_text(json.dumps({"best_model": best_name, "models": results}, indent=2) + "\n")
    return {"best_model": best_name, "models": results}


def train_segment_model(customers: pd.DataFrame) -> None:
    features = customers[SEGMENT_FEATURES].astype(float)
    scaler = StandardScaler()
    scaled = scaler.fit_transform(features)
    upper_bound = min(8, len(features) - 1)
    scores = {}
    for cluster_count in range(2, upper_bound + 1):
        candidate = KMeans(n_clusters=cluster_count, n_init=10, random_state=42)
        labels = candidate.fit_predict(scaled)
        scores[cluster_count] = float(silhouette_score(scaled, labels))
    best_cluster_count = max(scores, key=scores.get)
    if 4 in scores and scores[4] >= scores[best_cluster_count] - 0.01:
        best_cluster_count = 4
    pipeline = make_pipeline(StandardScaler(), KMeans(n_clusters=best_cluster_count, n_init=10, random_state=42))
    pipeline.fit(features)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": pipeline, "features": SEGMENT_FEATURES, "cluster_count": best_cluster_count, "silhouette_scores": scores}, SEGMENT_MODEL)
    (MODEL_DIR / "segmentation_metrics.json").write_text(json.dumps({
        "selected_clusters": best_cluster_count,
        "selection_reason": "Four actionable customer tiers were selected because their silhouette score is within 0.01 of the best candidate.",
        "silhouette_scores": scores,
    }, indent=2) + "\n")


def load_purchase_model():
    return joblib.load(PURCHASE_MODEL) if PURCHASE_MODEL.exists() else None


def predict_purchase(customer, product, activity) -> float:
    bundle = load_purchase_model()
    if not bundle:
        raise RuntimeError("Purchase model is unavailable")
    values = [[
        customer.age, customer.total_purchases, customer.total_spending, customer.average_order_value,
        customer.website_visits, product.price, product.rating,
        activity.product_views if activity else 0,
        activity.cart_additions if activity else 0,
        activity.wishlist_additions if activity else 0,
        activity.previous_purchases if activity else 0,
        activity.time_spent if activity else 0,
    ]]
    return float(bundle["model"].predict_proba(pd.DataFrame(values, columns=FEATURES))[0, 1])


def segment_customer(customer) -> str:
    bundle = joblib.load(SEGMENT_MODEL) if SEGMENT_MODEL.exists() else None
    if not bundle:
        raise RuntimeError("Customer segmentation model is unavailable")
    frequency = customer.total_purchases / max((pd.Timestamp.now() - pd.Timestamp(customer.registration_date)).days / 30, 1)
    row = pd.DataFrame([[
        customer.total_purchases, customer.total_spending, customer.average_order_value,
        customer.website_visits, frequency,
    ]], columns=SEGMENT_FEATURES)
    model = bundle["model"]
    cluster = int(model.predict(row)[0])
    centers = model[-1].cluster_centers_
    value_order = np.argsort(centers[:, 1])
    rank = int(np.where(value_order == cluster)[0][0])
    if len(value_order) == 2:
        labels = ["At-Risk Customer", "Premium Customer"]
        return labels[rank]
    if len(value_order) == 3:
        labels = ["At-Risk Customer", "Regular Customer", "Premium Customer"]
        return labels[rank]
    labels = ["At-Risk Customer", "Occasional Customer", "Regular Customer", "Premium Customer"]
    return labels[min(rank * len(labels) // len(value_order), len(labels) - 1)]