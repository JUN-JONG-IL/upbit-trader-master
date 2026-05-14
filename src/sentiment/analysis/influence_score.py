# Backward compatibility shim
from .analytics.influence_score import *  # noqa: F401,F403
from .analytics.influence_score import InfluenceScoreCalculator, calculate_social_influence  # noqa: F401
