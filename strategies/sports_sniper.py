import os
import logging
from datetime import datetime
from strategies.base_strategy import BaseStrategy
from data.sports_client import sports_client

logger = logging.getLogger("SPORTS_SNIPER")

class SportsSniperEdge(BaseStrategy):
    def __init__(self):
        super().__init__()
        self.active_ticker = None

    @property
    def name(self) -> str:
        return "SPORTS_SNIPER"

    @property
    def ticker_prefix(self) -> str:
        return os.getenv("SPORTS_TICKER", "KXNBA")

    def get_prewarm_time(self) -> str:
        return "11:00:00"

    def get_execute_time(self) -> str:
        return "11:30:00"

    def is_active_today(self) -> bool:
        # 1. Gate on environment variable
        if os.getenv("SPORTS_ACTIVE", "false").lower() != "true":
            return False
            
        # 2. Gate on NBA Season (October through June)
        month = datetime.now().month
        if month in [7, 8, 9]:
            return False
            
        # 3. Gate on actual game availability today (Protected by 300s TTL cache)
        try:
            games = sports_client.get_todays_games("nba")
            if not games:
                return False
        except Exception as e:
            logger.error(f"[{self.name}] Failed to check active games: {str(e)}")
            return False
            
        return True

    def build_context(self) -> dict:
        # 1. Find the best game of the day
        try:
            best_game = sports_client.get_best_game("nba")
            if not best_game:
                logger.error(f"[{self.name}] No optimal games found.")
                return {} 
                
            game_id = best_game.get("game_id")
            if not game_id:
                return {}
        except Exception as e:
            logger.error(f"[{self.name}] Failed to resolve best game: {str(e)}")
            return {}

        # 2. Fetch Deep Context
        try:
            game_data = sports_client.get_game_context("nba", game_id)
        except Exception as e:
            logger.error(f"[{self.name}] Failed to fetch game context: {str(e)}")
            return {}

        # 3. Apply Hard Cap to Probabilities (Claude Fix 3)
        try:
            capped_home_prob = f"{min(float(game_data.get('home_implied_prob', '0.50')), 0.85):.2f}"
            capped_away_prob = f"{min(float(game_data.get('away_implied_prob', '0.50')), 0.85):.2f}"
        except (ValueError, TypeError):
            capped_home_prob = "0.50"
            capped_away_prob = "0.50"

        # 4. Build the LLM Prompt
        prompt = (
            f"You are a quantitative sports betting AI. Analyze the following NBA game and provide a trading signal.\n\n"
            f"--- GAME DATA ---\n"
            f"Home Team: {game_data.get('home_team')} (Home Rec: {game_data.get('home_home_record')}, Overall: {game_data.get('home_record')}, L5: {game_data.get('last_5_home')})\n"
            f"Away Team: {game_data.get('away_team')} (Away Rec: {game_data.get('away_away_record')}, Overall: {game_data.get('away_record')}, L5: {game_data.get('last_5_away')})\n"
            f"Home Implied Win Prob: {game_data.get('home_implied_prob')} (Decimal Odds: {game_data.get('home_ml_odds')})\n"
            f"Away Implied Win Prob: {game_data.get('away_implied_prob')} (Decimal Odds: {game_data.get('away_ml_odds')})\n"
            f"Elimination Game: {game_data.get('elimination_game')}\n"
            f"Series Summary: {game_data.get('series_summary')}\n"
            f"Key Injuries: {game_data.get('key_injury_flag')} - {game_data.get('injury_notes')}\n"
            f"Data Quality: {game_data.get('data_quality')}\n\n"
            f"--- SIGNAL MAPPING ---\n"
            f"BUY_YES = {game_data.get('home_team')} wins (Home Team)\n"
            f"BUY_NO = {game_data.get('away_team')} wins (Away Team)\n"
            f"WATCH = No edge or injury uncertainty\n\n"
            f"--- CONFIDENCE ANCHORS ---\n"
            f"90-100: Elimination game AND clear record advantage\n"
            f"75-89: Clear favorite AND records support\n"
            f"65-74: Slight edge, some uncertainty\n"
            f"Below 65: Output WATCH\n\n"
            f"--- EDGE SOURCES ---\n"
            f"Weigh ODDS, RECORDS, INJURIES, HOME_ADVANTAGE, and SERIES context.\n\n"
            f"--- ENTRY PRICE RULES ---\n"
            f"If BUY_YES: Use '{capped_home_prob}' as suggested_entry_dollars.\n"
            f"If BUY_NO: Use '{capped_away_prob}' as suggested_entry_dollars.\n"
            f"Value must be a string between '0.01' and '0.85'.\n\n"
            f"--- REQUIRED OUTPUT ---\n"
            f"Respond ONLY with valid JSON:\n"
            f"{{\n"
            f'  "signal": "BUY_YES" or "BUY_NO" or "WATCH",\n'
            f'  "confidence": integer 0-100,\n'
            f'  "suggested_entry_dollars": "0.XX",\n'
            f'  "risk_flag": "LOW" or "MEDIUM" or "HIGH",\n'
            f'  "edge_source": "ODDS" or "RECORDS" or "INJURIES" or "HOME_ADVANTAGE" or "SERIES",\n'
            f'  "reasoning": "2-3 sentences citing specific values"\n'
            f"}}\n"
            f"Entry price must be quoted string 0.01-0.99."
        )

        return {
            "prompt": prompt,
            "game_data": game_data,
            "ticker": self.ticker_prefix
        }
