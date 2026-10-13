"""MongoDB database connection and operations."""
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

_client = None
_db = None


def get_client():
    """Get or create MongoDB client."""
    global _client
    if _client is None:
        _client = MongoClient(
            settings.MONGODB_URI,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
        )
    return _client


def get_db():
    """Get database instance."""
    global _db
    if _db is None:
        client = get_client()
        _db = client[settings.MONGODB_DB]
    return _db


def check_connection() -> bool:
    """Check if MongoDB is reachable."""
    try:
        client = get_client()
        client.admin.command("ping")
        return True
    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        logger.warning(f"MongoDB connection failed: {e}")
        return False


def setup_indexes():
    """Create indexes for optimal query performance."""
    db = get_db()
    try:
        db.orders.create_index([("order_id", ASCENDING)], unique=True)
        db.orders.create_index([("customer_id", ASCENDING)])
        db.orders.create_index([("order_date", ASCENDING)])
        db.orders.create_index([("order_status", ASCENDING)])

        db.order_items.create_index([("order_item_id", ASCENDING)], unique=True)
        db.order_items.create_index([("order_id", ASCENDING)])
        db.order_items.create_index([("product_id", ASCENDING)])

        db.products.create_index([("product_id", ASCENDING)], unique=True)
        db.products.create_index([("category", ASCENDING)])

        db.customers.create_index([("customer_id", ASCENDING)], unique=True)
        db.customers.create_index([("region", ASCENDING)])
        db.customers.create_index([("country", ASCENDING)])

        db.returns.create_index([("return_id", ASCENDING)], unique=True)
        db.returns.create_index([("order_id", ASCENDING)])
        db.returns.create_index([("product_id", ASCENDING)])
        db.returns.create_index([("customer_id", ASCENDING)])
        db.returns.create_index([("return_reason", ASCENDING)])

        db.analysis_results.create_index([("analysis_type", ASCENDING)])
        db.data_quality_reports.create_index([("created_at", DESCENDING)])

        logger.info("MongoDB indexes created successfully")
    except Exception as e:
        logger.error(f"Error creating indexes: {e}")


def drop_all_collections():
    """Drop all collections (for reimport)."""
    db = get_db()
    for name in db.list_collection_names():
        db.drop_collection(name)
    logger.info("All collections dropped")
