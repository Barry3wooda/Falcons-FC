import os
import logging
import joblib
import pandas as pd
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

MODEL_PATH = os.path.join(settings.BASE_DIR, 'core', 'ml_models', 'dynamic_pricing_model.pkl')
FEATURES_PATH = os.path.join(settings.BASE_DIR, 'core', 'ml_models', 'feature_columns.pkl')

_model = None
_feature_columns = None


def get_model():
    global _model, _feature_columns
    if _model is None:
        try:
            _model = joblib.load(MODEL_PATH)
            _feature_columns = joblib.load(FEATURES_PATH)
            logger.info('ML pricing model loaded successfully.')
        except Exception as e:
            logger.error(f'Failed to load ML model: {e}')
            return None, None
    return _model, _feature_columns


def calculate_dynamic_price(match, section):
    """
    Calculates the ML-driven dynamic price for a given match + section.
    Falls back to base price if model is unavailable.
    """
    try:
        model, feature_columns = get_model()

        if model is None:
            logger.warning('ML model unavailable — using base price.')
            return float(section.base_price)

        days_until_match = (match.date.date() - timezone.now().date()).days
        days_until_match = max(days_until_match, 0)

        total_seats = section.total_seats()
        if total_seats == 0:
            return float(section.base_price)

        available = section.available_seats_for_match(match).count()
        booked = total_seats - available
        current_occupancy_rate = booked / total_seats

        league_tier = 1.5 if match.competition.competition_type in ['Cup', 'Derby'] else 1.0

        input_df = pd.DataFrame([{
            'days_until_match': days_until_match,
            'match_importance_score': match.match_importance_score,
            'league_tier': league_tier,
            'current_occupancy_rate': current_occupancy_rate,
        }])[feature_columns]

        demand_score = model.predict(input_df)[0]
        demand_score = max(0.0, min(1.0, float(demand_score)))

        final_price = float(section.base_price) * (1 + demand_score)
        return round(final_price, 2)

    except Exception as e:
        logger.error(f'Dynamic pricing error: {e}')
        return float(section.base_price)