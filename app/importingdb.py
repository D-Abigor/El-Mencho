"""
import_teams.py
--------------
Imports teams from a MongoDB JSON export into Postgres tables:
  - users
  - accounts (leaders get 1500 credits, members get 0)

Usage:
    pip install psycopg2-binary
    python import_teams.py

Set your DB connection string in the DATABASE_URL variable below.
"""

import json
import uuid
import psycopg2

# ── Config ────────────────────────────────────────────────────────────────────
JSON_FILE = "test1_teams.json"
DATABASE_URL = "postgresql://USER:PASSWORD@HOST:5432/DBNAME"
# ─────────────────────────────────────────────────────────────────────────────

# ── Score thresholds & leader bonuses ────────────────────────────────────────
# EDIT THESE VALUES before running:
STARTINGCREDS = 1500
THRESHOLD_A = 100      # score >= this → bonus X          [THRESHOLD A]
THRESHOLD_B = 500     # score >= this → bonus Y          [THRESHOLD B]
THRESHOLD_C = 900    # score >= this → bonus Z          [THRESHOLD C]
BONUS_X     = 1000    # bonus for threshold A            [BONUS X]
BONUS_Y     = 2000   # bonus for threshold B            [BONUS Y]
BONUS_Z     = 4000   # bonus for threshold C            [BONUS Z]
# Thresholds are evaluated highest-first (A > B > C). If none match, bonus = 0.
# ─────────────────────────────────────────────────────────────────────────────


def get_leader_bonus(team_score: int) -> int:
    """Return the bonus credits for a leader based on the team's total score."""
    if THRESHOLD_A<=team_score<=THRESHOLD_B:    # [THRESHOLD A]
        return BONUS_X               # [BONUS X]
    elif THRESHOLD_B <= team_score <= THRESHOLD_C:  # [THRESHOLD B]
        return BONUS_Y               # [BONUS Y]
    elif team_score >= THRESHOLD_C:  # [THRESHOLD C]
        return BONUS_Z               # [BONUS Z]
    return 0


def load_json(path: str) -> list:
    with open(path, "r") as f:
        return json.load(f)


def import_teams(conn, teams: list):
    with conn.cursor() as cur:
        inserted_users = 0
        inserted_accounts = 0

        for team in teams:
            team_id    = team["teamId"]           # used as affiliation
            players    = team.get("players", [])
            team_score = sum(p.get("points", 0) for p in players)  # sum of all player points
            bonus      = get_leader_bonus(team_score)

            print(f"  Team: {team_id} | Score: {team_score} | Leader bonus: +{bonus}")

            for player in players:
                user_uuid = str(uuid.uuid4())
                username   = player["playerId"]
                password   = player["password"]  # already bcrypt-hashed
                is_leader  = player["role"] == "Leader"
                balance    = (1500 + bonus) if is_leader else 0

                # ── Insert into users ─────────────────────────────────────
                cur.execute(
                    """
                    INSERT INTO users (id, username, password_hash, isleader, affiliation, access)
                    VALUES (%s, %s, %s, %s, %s, 'player')
                    ON CONFLICT (username) DO NOTHING
                    RETURNING id
                    """,
                    (user_uuid, username, password, is_leader, team_id),
                )
                row = cur.fetchone()

                # If the user already existed, skip account creation
                if row is None:
                    print(f"  [SKIP] {username} already exists — skipped.")
                    continue

                actual_uuid = row[0]  # use the id actually inserted
                inserted_users += 1

                # ── Insert into accounts ──────────────────────────────────
                cur.execute(
                    """
                    INSERT INTO accounts (user_id, balance)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id) DO NOTHING
                    """,
                    (actual_uuid, balance),
                )
                inserted_accounts += 1

                role_label = f"Leader ({STARTINGCREDS + bonus} creds)" if is_leader else "Member (0 creds)"
                print(f"  [OK]   {username} — {role_label}")

        conn.commit()
        print(f"\n✓ Done — {inserted_users} users and {inserted_accounts} accounts inserted.")


def main():
    print(f"Loading {JSON_FILE}...")
    teams = load_json(JSON_FILE)
    print(f"Found {len(teams)} team(s).\n")

    conn = psycopg2.connect(DATABASE_URL)
    try:
        import_teams(conn, teams)
    except Exception as e:
        conn.rollback()
        print(f"\n✗ Error — transaction rolled back.\n{e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()