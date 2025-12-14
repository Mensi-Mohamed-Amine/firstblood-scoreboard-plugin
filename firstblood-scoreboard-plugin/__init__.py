import requests
import re
import json
import logging
from functools import wraps
from flask import request
from flask.wrappers import Response
from CTFd.models import Challenges, Solves, Teams
from CTFd.utils.scores import get_team_standings
from CTFd.utils.dates import ctftime
from CTFd.utils import config as ctfd_config
from CTFd.utils.user import get_current_team, get_current_user

# =========================
# WEBHOOK & TOKEN CONFIG
# =========================
WEBHOOK = ""
TOKEN = ""

# =========================
# LOGGING CONFIG
# =========================
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [LIVESCOREBOARD] %(levelname)s: %(message)s"
)
logger = logging.getLogger(__name__)

# =========================
# SANITIZER
# =========================
sanreg = re.compile(r'(~|!|@|#|\$|%|\^|&|\*|\(|\)|\_|\+|\`|-|=|\[|\]|;|\'|,|\.|\/|\{|\}|\||:|"|<|>|\?)')
sanitize = lambda m: sanreg.sub(r"\1", m)

# =========================
# HTTP SEND WITH DEBUG
# =========================
def send(url, data):
    try:
        payload = json.dumps(data, default=str)
        logger.debug("Preparing POST request")
        logger.debug(f"URL: {url}")
        logger.debug(f"Payload: {payload}")
        response = requests.post(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Verify-CTFd": TOKEN
            },
            timeout=5
        )
        logger.debug(f"Response status: {response.status_code}")
        logger.debug(f"Response body: {response.text}")
    except Exception as e:
        logger.error(f"Failed sending data to {url}", exc_info=True)

# =========================
# MAIN PLUGIN LOADER
# =========================
def load(app):
    TEAMS_MODE = ctfd_config.is_teams_mode()
    logger.info("Loading LiveScoreboard plugin")

    if not WEBHOOK:
        logger.error("WEBHOOK not set — plugin disabled")
        return

    try:
        requests.get(WEBHOOK, timeout=5)
        logger.info("Webhook reachable")
    except Exception:
        logger.error("Webhook NOT reachable — plugin disabled", exc_info=True)
        return

    # =========================
    # DECORATOR
    # =========================
    def challenge_attempt_decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            result = f(*args, **kwargs)
            if not ctftime():
                logger.debug("CTF not started — skipping")
                return result
            if not isinstance(result, Response):
                return result
            data = result.json
            logger.debug(f"API response data: {data}")
            if not (
                isinstance(data, dict)
                and data.get("success") is True
                and isinstance(data.get("data"), dict)
                and data["data"].get("status") == "correct"
            ):
                return result

            # =========================
            # REQUEST DATA
            # =========================
            if request.content_type != "application/json":
                request_data = request.form
            else:
                request_data = request.get_json()
            logger.debug(f"Request content-type: {request.content_type}")
            logger.debug(f"Request data: {request_data}")
            challenge_id = request_data.get("challenge_id")
            challenge = Challenges.query.filter_by(id=challenge_id).first_or_404()

            # =========================
            # FIRST BLOOD CHECK
            # =========================
            solvers = Solves.query.filter_by(challenge_id=challenge.id)
            if TEAMS_MODE:
                solvers = solvers.filter(Solves.team.has(hidden=False))
            num_solves = solvers.count()
            first_blood = 1 if num_solves - 1 == 0 else 0
            logger.debug(
                f"Challenge {challenge_id} | "
                f"Solves before this: {num_solves - 1} | "
                f"First blood: {first_blood}"
            )

            # =========================
            # USER / TEAM
            # =========================
            team = get_current_team()
            user = get_current_user()
            if team and team.hidden:
                logger.debug("Hidden team — skipping webhook")
                return result

            submission = Solves.query.filter_by(
                account_id=user.account_id,
                challenge_id=challenge_id
            ).first()

            solve_details = [{
                "team": sanitize("" if team is None else team.name),
                "user": sanitize(user.name),
                "challenge": sanitize(challenge.name),
                "first_blood": first_blood,
                "date": str(submission.date)
            }]
            logger.debug(f"Solve payload: {solve_details}")

            # =========================
            # SCOREBOARD
            # =========================
            score = get_team_standings()
            score_result = format_scoreboard(score)
            logger.debug(f"Scoreboard payload: {score_result}")

            # =========================
            # SEND WEBHOOKS
            # =========================
            logger.info("Sending webhook data")
            send(WEBHOOK + "/api/solve", solve_details)
            send(WEBHOOK + "/api/scoreboard", score_result)

            return result
        return wrapper

    # =========================
    # SCOREBOARD FORMATTER
    # =========================
    def format_scoreboard(data):
        scoreboard = []
        for item in data:
            team_name = item[2]
            team = Teams.query.filter_by(name=team_name).first()
            if team is None:
                continue
            solves = team.get_solves()
            raw_score = item[3]
            score = 0 if raw_score is None else raw_score  # Handles None → 0

            scoreboard.append({
                "team": sanitize(team_name),
                "score": score,
                "num_solves": len(solves)
            })
        return scoreboard

    # =========================
    # APPLY DECORATOR
    # =========================
    app.view_functions["api.challenges_challenge_attempt"] = challenge_attempt_decorator(
        app.view_functions["api.challenges_challenge_attempt"]
    )
    logger.info("LiveScoreboard plugin loaded successfully")