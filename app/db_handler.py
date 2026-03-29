import asyncpg
import asyncio
import os
import uuid
from dotenv import load_dotenv
from passlib.hash import bcrypt
from exceptions import InvalidSession, dbError, couldNotGetUsernameAvailability, authenticationFailure, transactionError

load_dotenv()

conn_pool = None
tokenCleanFrequency = 180       # seconds between expired session sweeps
bcryptCost = 12                 # bcrypt work factor


# --------------------------- Init ------------------#

async def session_cleaner():
    while True:
        async with conn_pool.acquire() as conn:
            await conn.execute("DELETE FROM sessions WHERE expires_at < NOW();")
        await asyncio.sleep(tokenCleanFrequency)

async def init_conn_pool_and_cleaner():
    global conn_pool
    conn_pool = await asyncpg.create_pool(os.getenv("DB_URL"))
    asyncio.create_task(session_cleaner())


# ----------------- Internal Helper ----------------------#

async def _getuuid(username: str) -> str:
    async with conn_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM users WHERE username = $1;", username
        )
        if not row:
            raise dbError("Internal db error - could not get corresponding uuid for your username")
        return row["id"]   # keep as uuid.UUID


async def _uuidFromSession(session_token: str):
    async with conn_pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT user_id FROM sessions
               WHERE session_token = $1 AND expires_at > NOW();""",
            uuid.UUID(session_token),
        )
        if not row:
            raise InvalidSession("Session is invalid or has expired.")
        return row["user_id"]   # keep as uuid.UUID — asyncpg needs the native type


async def _getUsernameFromUuid(uuid_val) -> str:
    async with conn_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT username FROM users WHERE id = $1;", uuid_val
        )
        if not row:
            raise dbError("Internal db error - could not get corresponding username from uuid")
        return row["username"]

async def _getTeamnameFromUuid(uuid_val) -> str:
    async with conn_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT affiliation FROM users WHERE id = $1;", uuid_val
        )
        if not row:
            raise dbError("Internal db error - could not get corresponding teamname from uuid")
        return row["affiliation"]

def _gameLogstoDescriptive(gamelogs: list):
    cleanedLogs = []
    for entries in gamelogs:
        game = entries["game"]
        time = entries["timeoffinish"]
        credit_change = entries["finalamount"] - entries["initialbet"]
        if credit_change >= 0:
            line = f"You played {game} at {time} and won {abs(credit_change)} credits"
        else:
            line = f"You played {game} at {time} and lost {abs(credit_change)} credits"
        cleanedLogs.append(line)
    return cleanedLogs

def _transactionstoDescriptive(transactionlogs: list, uuid: str):
    cleanedLogs = []
    for entries in transactionlogs:          # FIX: was iterating over cleanedLogs
        change = entries["change"]
        source = str(entries["source"])
        destination = str(entries["destination"])
        if source == uuid:
            line = f"You sent {change} credits"
        elif destination == uuid:
            line = f"You received {change} credits"
        else:
            line = f"Transaction of {change} credits"
        cleanedLogs.append(line)
    return cleanedLogs

def _convertQueue(queue: list):
    queuecleaned = {}
    index = 1
    for players in queue:
        queuecleaned[index] = players["username"]   # FIX: was players[username]
        index += 1
    return queuecleaned

def _convertActivePlayers(activePlayers: list):
    players = {}
    for player in activePlayers:
        players[player["username"]] = player["bet"]
    return players

def _cleanUserQueue(activeQueue: list):
    queues = {}
    for queue in activeQueue:
        queues[queue["game"]] = queue["position"]
    for game in ['teenPatti', 'poker', 'spadesOf3', 'blackjack', 'rummy', 'crazy8s']:
        if game not in queues:
            queues[game] = -1
    return queues


# ------------------------ route helper functions ------------------------#

async def validate(session_token: str, role: str) -> bool:
    if not session_token:
        return False
    try:
        token_uuid = uuid.UUID(session_token)
    except ValueError:
        return False
    async with conn_pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT u.access
               FROM sessions s
               JOIN users u ON s.user_id = u.id
               WHERE s.session_token = $1 AND s.expires_at > NOW();""",
            token_uuid,
        )
    return bool(row and row["access"] == role)

async def getPayees(session_token: str):
    source_uuid = await _uuidFromSession(session_token)       # FIX: correct function name
    teamname = await _getTeamnameFromUuid(source_uuid)
    async with conn_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT username FROM users WHERE id != $1 AND affiliation = $2 ORDER BY username;",
            source_uuid, teamname
        )
    if not rows:
        raise dbError(f"Internal db error - could not get list of payees affiliated to {teamname}")
    return [r["username"] for r in rows]


async def getSessionToken(username: str, password: str):
    # input length guard — bcrypt silently truncates at 72 bytes
    if len(password.encode()) > 72:
        raise authenticationFailure("Password too long")

    async with conn_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, password_hash FROM users WHERE username = $1;", username
        )

        if row:
            valid = await asyncio.to_thread(
                bcrypt.verify, password, row["password_hash"]
            )
            if valid:
                existing = await conn.fetchrow(
                    """SELECT session_token FROM sessions
                       WHERE user_id = $1 AND expires_at > NOW();""",
                    row["id"],
                )
                if existing:
                    return existing["session_token"]
                new_session = await conn.fetchrow(
                    """INSERT INTO sessions (user_id, expires_at)
                       VALUES ($1, NOW() + INTERVAL '1 day')
                       RETURNING session_token;""",
                    row["id"],
                )
                return new_session["session_token"]
            else:
                raise authenticationFailure("Invalid credentials")
        else:
            raise authenticationFailure("Invalid credentials")   # FIX: don't leak user existence


async def deleteSessionToken(session_token: str):
    async with conn_pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM sessions WHERE session_token = $1;", uuid.UUID(session_token)
        )

async def transfer(session_id: str, destination_username: str, amount):
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        raise transactionError("Amount must be a whole number")
    if amount <= 0:
        raise transactionError("Amount must be greater than zero")

    source_uuid = await _uuidFromSession(session_id)         # FIX: correct name + await
    dest_uuid = await _getuuid(destination_username)

    if str(source_uuid) == str(dest_uuid):
        raise transactionError("Cannot transfer to yourself")

    async with conn_pool.acquire() as conn:
        try:
            async with conn.transaction():
                ids = sorted([source_uuid, dest_uuid], key=lambda x: str(x))
                await conn.fetchrow(
                    "SELECT balance FROM accounts WHERE user_id = $1 FOR UPDATE;",
                    ids[0],
                )
                await conn.fetchrow(
                    "SELECT balance FROM accounts WHERE user_id = $1 FOR UPDATE;",
                    ids[1],
                )

                src_row = await conn.fetchrow(
                    "SELECT balance FROM accounts WHERE user_id = $1;", source_uuid
                )
                if not src_row:
                    raise transactionError("Your account does not exist")

                dst_row = await conn.fetchrow(
                    "SELECT balance FROM accounts WHERE user_id = $1;", dest_uuid
                )
                if not dst_row:
                    raise transactionError("Recipient account does not exist")

                if src_row["balance"] < amount:
                    raise transactionError("Insufficient balance")    # FIX: was return, not raise

                await conn.execute(
                    "INSERT INTO transactions (change, source, destination) VALUES ($1, $2, $3);",
                    amount, source_uuid, dest_uuid,
                )
                await conn.execute(
                    "UPDATE accounts SET balance = balance - $1 WHERE user_id = $2;",
                    amount, source_uuid,
                )
                await conn.execute(
                    "UPDATE accounts SET balance = balance + $1 WHERE user_id = $2;",
                    amount, dest_uuid,
                )
                return True
        except transactionError:
            raise
        except Exception as e:
            raise transactionError(f"Transaction failed: {str(e)}")


async def getPlayerHome(session_token):
    userid = await _uuidFromSession(session_token)      # FIX: was missing await
    async with conn_pool.acquire() as conn:
        userDetails = await conn.fetchrow(
            """SELECT u.affiliation AS teamname, a.balance AS usercredits
            FROM users u JOIN accounts a ON u.id = a.user_id
            WHERE u.id = $1;""", userid
        )
        generalDetails = await conn.fetchrow(
            """SELECT SUM(a.balance) AS teamcredits
            FROM users u JOIN accounts a ON u.id = a.user_id
            WHERE u.affiliation = $1;""", userDetails["teamname"]
        )
        gameLogs = await conn.fetch(
            """SELECT
            b.game AS game, b.timeoffinish AS timeoffinish,
            a.initialbet AS initialbet, a.finalamount AS finalamount
            FROM gameplayerlogs a JOIN gamesplayed b ON a.gameid = b.gameid
            WHERE a.userid = $1
            ORDER BY b.timeoffinish DESC;""", userid
        )
        transactions = await conn.fetch(
            """SELECT t.change AS change, t.source AS source, t.destination AS destination
            FROM transactions t WHERE t.source = $1 OR t.destination = $1""",
            userid                                          # FIX: missing parameter
        )
    convertedTransactions = _transactionstoDescriptive(transactions, userid)
    convertedLogs = _gameLogstoDescriptive(gameLogs)
    return {
        "teamname": userDetails["teamname"],
        "usercredits": userDetails["usercredits"],
        "teamcredits": generalDetails["teamcredits"],
        "transactions": convertedTransactions,
        "gamelogs": convertedLogs
    }


async def getTableDetails(tablenum: str):
    async with conn_pool.acquire() as conn:
        queue = await conn.fetch(                            # FIX: missing await
            """SELECT u.username AS username FROM users u JOIN queue q
            ON q.userId = u.id WHERE q.tableId = $1 ORDER BY q.timeOfJoin ASC;""", int(tablenum)
        )
        activePlayers = await conn.fetch(                   # FIX: missing await
            """SELECT u.username AS username, a.betAmount AS bet
            FROM users u JOIN activeplayers a ON a.userid = u.id WHERE a.tableId = $1;""",
            int(tablenum)
        )

    playersCleaned = _convertActivePlayers(activePlayers)
    queueCleaned = _convertQueue(queue)

    return {
        "queue": queueCleaned,
        "players": playersCleaned
    }


async def getManagerHome(tablenum: str):
    return await getTableDetails(tablenum)


async def getUserQueue(session_token):
    uuid = await _uuidFromSession(session_token)
    async with conn_pool.acquire() as conn:
        activeQueues = await conn.fetch(                    # FIX: missing await
            """
            SELECT gameselected AS game, position
            FROM (
                SELECT
                    q.userid,
                    t.gameselected,
                    ROW_NUMBER() OVER (
                        PARTITION BY q.tableid
                        ORDER BY q.timeofjoin ASC
                    ) AS position
                FROM queue q
                JOIN tables t ON q.tableid = t.tableid
            ) sub
            WHERE userid = $1;
            """, uuid
        )
    cleanedUserQueue = _cleanUserQueue(activeQueues)
    return cleanedUserQueue


async def removeFromQueue(username: str, game: str):
    uuid = await _getuuid(username)                         # FIX: missing await
    async with conn_pool.acquire() as conn:
        await conn.execute(                                 # FIX: missing await
            "DELETE FROM queue WHERE userid = $1 AND tableId IN (SELECT tableid FROM tables WHERE gameselected = $2);",
            uuid, game
        )


async def insertIntoQueue(session_token: str, tablenum: str):
    userId = await _uuidFromSession(session_token)          # FIX: missing await
    async with conn_pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO queue(tableid, userid)
            VALUES($1, $2)""",
            int(tablenum), userId
        )


async def confirmPlayers(numberOfPlayers: int, tablenum: str):
    """
    Pick the first numberOfPlayers from the queue for this table,
    mark them readyToJoin so the frontend can prompt them to confirm.
    """
    async with conn_pool.acquire() as conn:
        # Grab the first N players by join time
        rows = await conn.fetch(
            """SELECT userid FROM queue
               WHERE tableid = $1
               ORDER BY timeofjoin ASC
               LIMIT $2;""",
            int(tablenum), numberOfPlayers
        )
        if not rows:
            raise dbError(f"No players in queue for table {tablenum}")

        selected_ids = [str(r["userid"]) for r in rows]

        # Mark them as readyToJoin
        await conn.execute(
            """UPDATE queue SET readytojoin = TRUE
               WHERE tableid = $1 AND userid = ANY($2::uuid[]);""",
            int(tablenum), selected_ids
        )
    return selected_ids


async def confirmParticipation(session_token: str, tablenum: str, confirmation: bool, betAmount: str = "0"):
    uuid = await _uuidFromSession(session_token)            # FIX: missing await
    async with conn_pool.acquire() as conn:
        if confirmation:
            try:
                bet = int(betAmount)
            except (TypeError, ValueError):
                raise transactionError("Bet amount must be a whole number")
            if bet <= 0:
                raise transactionError("Bet amount must be greater than zero")

            # Check player has enough balance
            balance_row = await conn.fetchrow(
                "SELECT balance FROM accounts WHERE user_id = $1;", uuid
            )
            if not balance_row or balance_row["balance"] < bet:
                raise transactionError("Insufficient balance to place this bet")

            response = await conn.execute(
                """INSERT INTO activeplayers(userid, tableid, betamount)
                VALUES($1, $2, $3)
                ON CONFLICT (userid) DO UPDATE SET tableid = $2, betamount = $3;""",
                uuid, int(tablenum), bet
            )
            # Remove from queue after confirming
            await conn.execute(
                "DELETE FROM queue WHERE userid = $1 AND tableid = $2;",
                uuid, int(tablenum)
            )
            if not response.endswith("1"):
                raise dbError(f"Could not confirm participation for table {tablenum}")
        else:
            await conn.execute(
                "DELETE FROM queue WHERE userid = $1 AND tableid = $2;",
                uuid, int(tablenum)
            )
    return True


async def startGame(players: list, tablenum: str):
    """
    Transition the table to 'active', deduct bets from balances,
    and insert a new gamesPlayed record. Returns the new gameId.
    """
    async with conn_pool.acquire() as conn:
        # Get the game selected for this table
        table_row = await conn.fetchrow(
            "SELECT gameselected FROM tables WHERE tableid = $1;", int(tablenum)
        )
        if not table_row:
            raise dbError(f"Table {tablenum} does not exist")
        game = table_row["gameselected"]
        if not game:
            raise dbError(f"No game selected for table {tablenum}")

        async with conn.transaction():
            # Mark table active
            await conn.execute(
                "UPDATE tables SET status = 'active' WHERE tableid = $1;",
                int(tablenum)
            )
            # Create game log entry
            game_row = await conn.fetchrow(
                """INSERT INTO gamesplayed(game, tableid)
                   VALUES($1, $2) RETURNING gameid;""",
                game, int(tablenum)
            )
            game_id = str(game_row["gameid"])

            # Deduct bets from player balances and write initial gamePlayerLogs rows
            for player_uuid in players:
                bet_row = await conn.fetchrow(
                    "SELECT betamount FROM activeplayers WHERE userid = $1 AND tableid = $2;",
                    player_uuid, int(tablenum)
                )
                if not bet_row:
                    raise dbError(f"Could not find bet for player {player_uuid}")
                bet = bet_row["betamount"]
                await conn.execute(
                    "UPDATE accounts SET balance = balance - $1 WHERE user_id = $2;",
                    bet, player_uuid
                )
                await conn.execute(
                    """INSERT INTO gameplayerlogs(gameid, userid, initialbet, finalamount)
                       VALUES($1, $2, $3, 0);""",
                    game_id, player_uuid, bet
                )

    return game_id


async def endGame(results: dict, tablenum: str):
    """
    results: { player_uuid: final_amount, ... }
    Pays out winnings, writes final amounts to logs, cleans up activePlayers,
    resets the table to waiting.
    """
    async with conn_pool.acquire() as conn:
        async with conn.transaction():
            # Get the most recent game for this table
            game_row = await conn.fetchrow(
                """SELECT gameid FROM gamesplayed
                   WHERE tableid = $1
                   ORDER BY timeoffinish DESC LIMIT 1;""",
                int(tablenum)
            )
            if not game_row:
                raise dbError(f"No active game found for table {tablenum}")
            game_id = str(game_row["gameid"])

            for player_uuid, final_amount in results.items():
                final_amount = int(final_amount)
                # Credit the final amount back to the player
                await conn.execute(
                    "UPDATE accounts SET balance = balance + $1 WHERE user_id = $2;",
                    final_amount, player_uuid
                )
                # Update the log
                await conn.execute(
                    """UPDATE gameplayerlogs SET finalamount = $1
                       WHERE gameid = $2 AND userid = $3;""",
                    final_amount, game_id, player_uuid
                )

            # Clean up activePlayers for this table
            await conn.execute(
                "DELETE FROM activeplayers WHERE tableid = $1;", int(tablenum)
            )
            # Reset table
            await conn.execute(
                "UPDATE tables SET status = 'waiting', gameselected = '' WHERE tableid = $1;",
                int(tablenum)
            )

    return True


async def getParticipation(session_token: str):
    """
    Returns tables where the player has been marked readyToJoin,
    so the frontend can prompt them to confirm.
    """
    uuid = await _uuidFromSession(session_token)
    async with conn_pool.acquire() as conn:
        rows = await conn.fetch(                            # FIX: was incomplete
            """SELECT q.tableid, t.gameselected
               FROM queue q
               JOIN tables t ON q.tableid = t.tableid
               WHERE q.userid = $1 AND q.readytojoin = TRUE;""",
            uuid
        )
    return [{"tableId": r["tableid"], "game": r["gameselected"]} for r in rows]


async def setGameForTable(tablenum: str, game: str):
    async with conn_pool.acquire() as conn:
        response = await conn.execute(
            "UPDATE tables SET gameselected = $1 WHERE tableid = $2;",   # FIX: missing SET keyword
            game, int(tablenum)
        )
        if not response.endswith("1"):
            raise dbError(f"Could not set game as {game} for table {tablenum}")


async def setMaxPlayersForTable(tablenum: str, max_players: int):
    async with conn_pool.acquire() as conn:
        await conn.execute(
            "UPDATE tables SET max_players = $1 WHERE tableid = $2;",     # FIX: missing SET keyword
            int(max_players), int(tablenum)
        )
