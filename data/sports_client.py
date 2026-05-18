import os
import time
import requests
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("SPORTS_CLIENT")

class SportsClient:
    def __init__(self):
        self._cache = {}
        self.cache_ttl = 300
        
        self.espn_base = {
            "NBA": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba",
            "NFL": "https://site.api.espn.com/apis/site/v2/sports/football/nfl",
            "MLB": "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb"
        }
        
        self.odds_sports = {
            "NBA": "basketball_nba",
            "NFL": "americanfootball_nfl",
            "MLB": "baseball_mlb"
        }

    def _convert_decimal_to_prob(self, decimal_odds: float) -> str:
        try:
            odds_val = float(decimal_odds)
            if odds_val <= 0: return "0.00"
            prob = 1 / odds_val
            return f"{prob:.2f}"
        except Exception:
            return "0.00"

    def _utc_to_et_string(self, iso_string: str) -> str:
        try:
            iso_string = iso_string.replace('Z', '+00:00')
            dt_utc = datetime.fromisoformat(iso_string)
            offset = 4 if 3 <= dt_utc.month <= 11 else 5
            dt_et = dt_utc - timedelta(hours=offset) 
            return dt_et.strftime("%I:%M %p ET")
        except Exception:
            return "Unknown Time"

    def get_todays_games(self, sport: str = "nba") -> list:
        base_url = self.espn_base.get(sport.upper())
        if not base_url: return []

        url = f"{base_url}/scoreboard"
        games = []

        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                for event in data.get("events", []):
                    comp = event.get("competitions", [{}])[0]
                    competitors = comp.get("competitors", [])
                    
                    home_team = away_team = "Unknown"
                    home_rec = away_rec = "0-0"
                    home_score = away_score = "0"
                    
                    for team in competitors:
                        is_home = team.get("homeAway") == "home"
                        name = team.get("team", {}).get("displayName", "Unknown")
                        score = team.get("score", "0")
                        rec_arr = team.get("records", [])
                        record = rec_arr[0].get("summary", "0-0") if rec_arr else "0-0"
                        
                        if is_home:
                            home_team, home_rec, home_score = name, record, score
                        else:
                            away_team, away_rec, away_score = name, record, score

                    status_str = event.get("status", {}).get("type", {}).get("description", "scheduled").lower()
                    venue = comp.get("venue", {}).get("fullName", "Unknown")
                    start_time = self._utc_to_et_string(event.get("date", ""))
                    
                    notes_data = comp.get("notes", [])
                    if isinstance(notes_data, list):
                        notes = " ".join([n.get("headline", "") for n in notes_data if isinstance(n, dict)]).lower()
                    else:
                        notes = ""
                        
                    series_data = comp.get("series", {})
                    series_summary = ""
                    if isinstance(series_data, list) and len(series_data) > 0:
                        series_summary = series_data[0].get("summary", "")
                    elif isinstance(series_data, dict):
                        series_summary = series_data.get("summary", "")
                        
                    elim_game = "game 7" in notes or "elimination" in notes or "elimination" in series_summary.lower()

                    games.append({
                        "game_id": str(event.get("id")),
                        "home_team": str(home_team),
                        "away_team": str(away_team),
                        "home_record": str(home_rec),
                        "away_record": str(away_rec),
                        "venue": str(venue),
                        "start_time_et": str(start_time),
                        "status": str(status_str),
                        "home_score": str(home_score),
                        "away_score": str(away_score),
                        "elimination_game": elim_game,
                        "series_summary": str(series_summary)
                    })
        except Exception as e:
            logger.error(f"Failed to fetch {sport} games from ESPN: {str(e)}")
        
        return games

    def get_best_game(self, sport: str) -> dict:
        games = self.get_todays_games(sport)
        if not games: return {}

        def score_game(g):
            score = 0
            if g.get("elimination_game"): score += 1000
            try:
                hw, hl = map(int, g.get("home_record", "0-0").split("-"))
                aw, al = map(int, g.get("away_record", "0-0").split("-"))
                h_pct = hw / (hw + hl) if (hw + hl) > 0 else 0
                a_pct = aw / (aw + al) if (aw + al) > 0 else 0
                score += abs(h_pct - a_pct) * 100
            except Exception: pass
            return score

        games.sort(key=score_game, reverse=True)
        return games[0]

    def get_injury_report(self, sport: str, team_id: str) -> dict:
        base_url = self.espn_base.get(sport.upper())
        if not base_url: return {"key_injury_flag": False, "injury_notes": ""}
        
        url = f"{base_url}/teams/{team_id}/roster"
        injured_players = []
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                athletes = r.json().get("athletes", [])
                for category in athletes:
                    for item in category.get("items", []):
                        injuries = item.get("injuries", [])
                        if injuries:
                            status = injuries[0].get("status", "Out")
                            injured_players.append(f"{item.get('fullName')} ({status})")
        except Exception as e:
            logger.error(f"Failed to fetch injury report for team {team_id}: {str(e)}")
            
        return {"key_injury_flag": len(injured_players) > 0, "injury_notes": " | ".join(injured_players)}

    def get_game_context(self, sport: str, game_id: str) -> dict:
        cache_key = f"{sport}_{game_id}_ctx"
        if cache_key in self._cache:
            cache_time, cached_data = self._cache[cache_key]
            if time.time() - cache_time < self.cache_ttl:
                return cached_data

        context = {
            "game_id": str(game_id), "data_quality": "PARTIAL",
            "home_home_record": "0-0", "away_away_record": "0-0",
            "last_5_home": "0-0", "last_5_away": "0-0",
            "series_summary": "", "elimination_game": False,
            "key_injury_flag": False, "injury_notes": ""
        }
        base_url = self.espn_base.get(sport.upper())

        if base_url:
            try:
                summary_url = f"{base_url}/summary?event={game_id}"
                r = requests.get(summary_url, timeout=5)
                if r.status_code == 200:
                    data = r.json()
                    box = data.get("boxscore", {}).get("teams", [])
                    if len(box) >= 2:
                        context["away_team"] = box[0].get("team", {}).get("displayName", "Unknown")
                        context["home_team"] = box[1].get("team", {}).get("displayName", "Unknown")

                    for team_meta in data.get("header", {}).get("competitions", [{}])[0].get("competitors", []):
                        is_home = team_meta.get("homeAway") == "home"
                        for rec in team_meta.get("records", []):
                            rec_type = rec.get("type", "")
                            rec_sum = rec.get("summary", "0-0")
                            if rec_type == "home" and is_home: context["home_home_record"] = rec_sum
                            if rec_type == "road" and not is_home: context["away_away_record"] = rec_sum
                            if "last" in rec_type.lower():
                                if is_home: context["last_5_home"] = rec_sum
                                else: context["last_5_away"] = rec_sum

                    header_comp = data.get("header", {}).get("competitions", [{}])[0]
                    
                    series_data = header_comp.get("series", {})
                    if isinstance(series_data, list) and len(series_data) > 0:
                        context["series_summary"] = series_data[0].get("summary", "")
                    elif isinstance(series_data, dict):
                        context["series_summary"] = series_data.get("summary", "")
                    
                    notes_data = header_comp.get("notes", [])
                    if isinstance(notes_data, list):
                        notes = " ".join([n.get("headline", "") for n in notes_data if isinstance(n, dict)]).lower()
                    else:
                        notes = ""
                        
                    context["elimination_game"] = "game 7" in notes or "elimination" in notes or "elimination" in context["series_summary"].lower()
                    
                    if "out" in notes or "injury" in notes:
                        context["injury_notes"] += f" [Notes Fallback: {notes}]"
                        context["key_injury_flag"] = True

            except Exception as e:
                logger.error(f"ESPN summary failed for {game_id}: {str(e)}")

        odds_api_key = os.getenv("ODDS_API_KEY")
        odds_sport_key = self.odds_sports.get(sport.upper())
        if odds_api_key and odds_sport_key and context.get("home_team"):
            try:
                odds_url = f"https://api.the-odds-api.com/v4/sports/{odds_sport_key}/odds/"
                params = {"apiKey": odds_api_key, "regions": "us", "markets": "h2h"}
                r = requests.get(odds_url, params=params, timeout=5)
                
                if r.status_code == 200:
                    odds_data = r.json()
                    for match in odds_data:
                        if context["home_team"] in match.get("home_team", ""):
                            for bookmaker in match.get("bookmakers", []):
                                for market in bookmaker.get("markets", []):
                                    if market.get("key") == "h2h":
                                        for outcome in market.get("outcomes", []):
                                            name = outcome.get("name", "")
                                            price = outcome.get("price", 0)
                                            if context["home_team"] in name:
                                                context["home_ml_odds"] = str(price)
                                                context["home_implied_prob"] = self._convert_decimal_to_prob(price)
                                            else:
                                                context["away_ml_odds"] = str(price)
                                                context["away_implied_prob"] = self._convert_decimal_to_prob(price)
                            context["data_quality"] = "FULL"
                            break
            except Exception as e:
                logger.error(f"Odds API fetch failed: {str(e)}")

        self._cache[cache_key] = (time.time(), context)
        return context

sports_client = SportsClient()
