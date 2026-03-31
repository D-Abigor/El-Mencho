import asyncpg
import asyncio
import os
import uuid as _uuid
from dotenv import load_dotenv
from passlib.hash import bcrypt
from errors import InvalidSession, DbError, CouldNotGetUsernameAvailability, AuthenticationFailure, TransactionError

load_dotenv()

conn_pool = None
tokenCleanFrequency = 180       # seconds between expired session sweeps
bcryptCost = 12                 # bcrypt work factor


#--------------------------- Init ------------------#

async def session_cleaner():
    while True:
        async with conn_pool.acquire() as conn:
            await conn.execute("DELETE FROM sessions WHERE expires_at < NOW();")
        await asyncio.sleep(tokenCleanFrequency)

async def init_conn_pool_and_cleaner():
    global conn_pool
    conn_pool = await asyncpg.create_pool(os.getenv("DB_URL"))
    asyncio.create_task(session_cleaner())


#----------------- Internal Helpers ----------------------#

def _parse_uuid(value: str) -> _uuid.UUID:
    """Parse a string to uuid.UUID, raising InvalidSession on failure."""
    try:
        return _uuid.UUID(str(value))
    except (TypeError, ValueError):
        raise InvalidSession("Session invalid or expired")


async def _uuidFromSession(session_token: str) -> _uuid.UUID:
    token = _parse_uuid(session_token)
    async with conn_pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT user_id FROM sessions
               WHERE session_token = $1 AND expires_at > NOW();""",
            token,
        )
        if not row:
            raise InvalidSession("Session invalid or expired")
        return row["user_id"]          # asyncpg returns uuid.UUID — keep native type


async def _getuuid(username: str) -> _uuid.UUID:
    async with conn_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM users WHERE username = $1;", username
        )
        if not row:
            raise DbError("Internal db error - could not get corresponding uuid for your username")
        return row["id"]               # uuid.UUID


async def _getUsernameFromUuid(uuid: _uuid.UUID) -> str:
    async with conn_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT username FROM users WHERE id = $1;", uuid
        )
        if not row:
            raise DbError("Internal db error - could not get corresponding username from uuid")
        return row["username"]


async def _getTeamnameFromUuid(uuid: _uuid.UUID) -> str:
    async with conn_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT affiliation FROM users WHERE id = $1;", uuid
        )
        if not row:
            raise DbError("Internal db error - could not get corresponding teamname from uuid")
        return row["affiliation"]


def _gameLogstoDescriptive(gamelogs: list[asyncpg.Record]):
    cleanedLogs = []
    for entry in gamelogs:
        game = entry["game"]
        time = entry["timeoffinish"]
        creditChange = entry["finalamount"] - entry["initialbet"]
        if creditChange >= 0:
            line = f"you played {game} at {time} and won {abs(creditChange)}"
        else:
            line = f"you played {game} at {time} and lost {abs(creditChange)}"
        cleanedLogs.append(line)
    return cleanedLogs


def _transactionstoDescriptive(transactionlogs: list[asyncpg.Record], uuid: _uuid.UUID):
    cleanedLogs = []
    for entry in transactionlogs:
        change = entry["change"]
        source = entry["source"]
        destination = entry["destination"]
        destinationusername = entry["destinationusername"]
        sourceusername = entry["sourceusername"]
        if source == uuid:
            line = f"you sent {destinationusername} {change}"
        elif destination == uuid:
            line = f"{sourceusername} sent you {change}"
        cleanedLogs.append(line)
    return cleanedLogs


def _convertQueue(queue: list[asyncpg.Record]):
    queueCleaned = {}
    if not queue:
        return {}
    for index, player in enumerate(queue, start=1):
        queueCleaned[index] = player["username"]
    return queueCleaned


def _convertActivePlayers(activePlayers: list[asyncpg.Record]):
    players = {}
    if not activePlayers:
        return {}
    for player in activePlayers:
        players[player["username"]] = player["bet"]
    return players


def _cleanUserQueue(activeQueue: list[asyncpg.Record]):
    queues = {}
    for queue in activeQueue:
        queues[queue["tableid"]] = {"game": queue["game"], "position": queue["position"], "length": queue["length"]}
    return queues


#------------------------ Route helper functions ------------------------#

async def validate(session_token: str, role: str) -> bool:
    try:
        token = _uuid.UUID(str(session_token))
    except (TypeError, ValueError):
        return False
    async with conn_pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT u.access
               FROM sessions s
               JOIN users u ON s.user_id = u.id
               WHERE s.session_token = $1 AND s.expires_at > NOW();""",
            token,
        )
    return bool(row and row["access"] == role)


async def getPayees(session_token: str):
    token = _parse_uuid(session_token)
    async with conn_pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT u2.username
               FROM sessions s
               JOIN users u1 ON s.user_id = u1.id
               JOIN users u2 ON u2.affiliation = u1.affiliation AND u2.id != u1.id
               WHERE s.session_token = $1 AND s.expires_at > NOW()
               ORDER BY u2.username;""",
            token
        )
    if not rows:
        raise DbError("Internal db error - could not get list of payees")
    return [r["username"] for r in rows]


async def getSessionToken(username: str, password: str):
    # input length guard — bcrypt silently truncates at 72 bytes
    if len(password.encode()) > 72:
        raise AuthenticationFailure("Password too long")

    async with conn_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, password_hash FROM users WHERE username = $1;", username
        )
        

        if row:
            valid = await asyncio.to_thread(
                bcrypt.verify, password, str(row["password_hash"])
            )
            if valid:
                new_session = await conn.fetchrow(
                    """INSERT INTO sessions (user_id, expires_at)
                       VALUES ($1, NOW() + INTERVAL '1 day')
                       RETURNING session_token;""",
                    row["id"]
                )
                return new_session["session_token"]
            else:
                raise AuthenticationFailure("Invalid credentials")
        else:
            try:
                raise DbError("db error - user does not exist")
            except Exception as e:
                print(f"Exception type: {type(e)}, MRO: {type(e).__mro__}")
                raise


async def deleteSessionToken(session_token: str):
    try:
        token = _uuid.UUID(str(session_token))
    except (TypeError, ValueError):
        return  # nothing to delete for a malformed token
    async with conn_pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM sessions WHERE session_token = $1;", token
        )


async def getAccess(session_token: str):
    async with conn_pool.acquire() as conn:
        row = await conn.fetchrow("""SELECT u.access AS access FROM users u JOIN sessions s ON u.id = s.user_id WHERE s.session_token = $1;""", session_token)
        return row["access"]

async def transfer(session_id: str, destination_username: str, amount):
    # validate transfer amount
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        raise TransactionError("Amount must be a whole number")
    if amount <= 0:
        raise TransactionError("Amount must be greater than zero")

    source_uuid = await _uuidFromSession(session_id)
    dest_uuid = await _getuuid(destination_username)

    if source_uuid == dest_uuid:
        raise TransactionError("Cannot transfer to yourself")

    async with conn_pool.acquire() as conn:
        try:
            async with conn.transaction():
                # Lock both rows in consistent UUID order to prevent deadlock
                ids = sorted([source_uuid, dest_uuid], key=lambda u: str(u))
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
                    raise TransactionError("Your account does not exist")

                dst_row = await conn.fetchrow(
                    "SELECT balance FROM accounts WHERE user_id = $1;", dest_uuid
                )
                if not dst_row:
                    raise TransactionError("Recipient account does not exist")

                if src_row["balance"] < amount:
                    raise TransactionError("Insufficient balance")

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
        except Exception as e:
            raise TransactionError(f"Transaction failed: {str(e)}")


async def getPlayerHome(session_token: str):
    async with conn_pool.acquire() as conn:
        uuid = await _uuidFromSession(session_token)

        userAndTeam = await conn.fetchrow(
            """SELECT
                u.affiliation AS teamname,
                a.balance AS userCredits,
                SUM(a2.balance) OVER (PARTITION BY u.affiliation) AS teamCredits
               FROM users u
               JOIN accounts a ON u.id = a.user_id
               JOIN users u2 ON u2.affiliation = u.affiliation
               JOIN accounts a2 ON u2.id = a2.user_id
               WHERE u.id = $1
               LIMIT 1;""",
            uuid
        )

        gameLogs = await conn.fetch(
            """SELECT
                gp.game AS game,
                gp.timeOfFinish AS timeOfFinish,
                gpl.initialBet AS initialBet,
                gpl.finalAmount AS finalAmount
               FROM gamePlayerLogs gpl
               JOIN gamesPlayed gp ON gpl.gameId = gp.gameId
               WHERE gpl.userId = $1
               ORDER BY gp.timeOfFinish DESC;""",
            uuid
        )

        transactions = await conn.fetch(
            """SELECT t.change, u1.username as sourceusername, t.source as source, u2.username as destinationusername, t.destination as destination
               FROM transactions t JOIN users u1 ON t.source = u1.id JOIN users u2 ON t.destination = u2.id
               WHERE t.source = $1 OR t.destination = $1
               ORDER BY processed_at DESC;""",
            uuid
        )

    return {
        "teamname": userAndTeam["teamname"],
        "usercredits": userAndTeam["usercredits"],
        "teamcredits": userAndTeam["teamcredits"],
        "transactions": _transactionstoDescriptive(transactions, uuid),
        "gamelogs": _gameLogstoDescriptive(gameLogs)
    }

async def getUserQueue(session_token: str):
    uuid = await _uuidFromSession(session_token)
    async with conn_pool.acquire() as conn:
        activeQueues = await conn.fetch(
            """SELECT 
                t.tableId AS tableid,
                t.gameSelected AS game,
                COALESCE(sq.length, 0) AS length,
                COALESCE(uq.position, -1) AS position
            FROM tables t
            LEFT JOIN (
                SELECT tableId, COUNT(*) AS length
                FROM queue
                GROUP BY tableId
            ) sq ON sq.tableId = t.tableId
            LEFT JOIN (
                SELECT tableId,
           ROW_NUMBER() OVER (PARTITION BY tableId ORDER BY timeOfJoin ASC) AS position
            FROM queue
            WHERE userId = $1
            ) uq ON uq.tableId = t.tableId;""",uuid
        )
    return _cleanUserQueue(activeQueues)


async def getLeaderBoard():
    async with conn_pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT u.affiliation AS teamname, SUM(a.balance) AS totalCredits
               FROM users u
               JOIN accounts a ON u.id = a.user_id
               WHERE access = 'player'
               GROUP BY u.affiliation
               ORDER BY totalCredits DESC;"""
        )
    return [{"teamname": r["teamname"], "totalCredits": r["totalcredits"]} for r in rows]


#------------- Functions serving player game endpoints --------------#

async def insertIntoQueue(session_token: str, tablenum: str):
    userId = await _uuidFromSession(session_token)
    async with conn_pool.acquire() as conn:
        status = await conn.fetchrow("""SELECT tableid FROM queue WHERE userid = $1 AND tableid = $2
            UNION
            SELECT tableid FROM activePlayers WHERE userid = $1;""",  # changed tableId dependency, so now if player is on active status for any table they wont be inserted into queue
            userId, tablenum)
        if status:
            return {"status": "already in queue or active in a game"}
        else:
            await conn.execute("""INSERT INTO queue (tableId, userId) VALUES ($1, $2);""",
            tablenum, userId
        )
        return {"status": "ok"}


async def confirmParticipation(session_token: str, tablenum: str, confirmation: bool, betAmount: str):
    # get user confirmation before moving player into game table; dropped from queue otherwise
    uuid = await _uuidFromSession(session_token)
    async with conn_pool.acquire() as conn:
        if confirmation:
            try:
                betAmount = int(betAmount)
            except (TypeError, ValueError):
                raise TransactionError("Bet amount must be a whole number")
            if betAmount <= 0:
                raise TransactionError("Bet amount must be greater than zero")
            
            async with conn.transaction():
                balance_row = await conn.fetchrow(
                    "SELECT balance FROM accounts WHERE user_id = $1 FOR UPDATE;", uuid
                )
                if not balance_row:
                    raise DbError("Account not found")
                if balance_row["balance"] < betAmount:
                    raise TransactionError("Insufficient balance to place bet")
                await conn.execute(
                    "UPDATE accounts SET balance = balance - $1 WHERE user_id = $2;",
                    betAmount, uuid
                )
                response = await conn.execute(
                    """INSERT INTO activePlayers (userId, tableId, betAmount)
                       VALUES ($1, $2, $3);""",
                    uuid, tablenum, betAmount
                )
                if not response.endswith("1"):
                    raise DbError(f"Could not confirm participation for table {tablenum}")
                await conn.execute(
                    "DELETE FROM queue WHERE userId = $1 AND tableId = $2;",
                    uuid, tablenum
                )
        else:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM queue WHERE userId = $1 AND tableId = $2;",
                    uuid, tablenum
                )
                await conn.execute(
                    """UPDATE queue q
                       SET readyToJoin = TRUE
                       WHERE q.number = (
                           SELECT MIN(next.number)
                           FROM queue next
                           WHERE next.tableId = $1
                             AND next.readyToJoin = FALSE
                       );""",
                    tablenum
                )

async def getParticipation(session_token: str):
    uuid = await _uuidFromSession(session_token)
    async with conn_pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT q.tableId AS "tableId", q.readyToJoin AS "readyToJoin"
                FROM (
                    SELECT tableId, readyToJoin
                    FROM queue
                WHERE userId = $1
                ) q""",
            uuid
        )
    return [dict(r) for r in rows]


#------------- Functions serving manager GET endpoints --------------#

async def getTablesForManager():
    async with conn_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT tableId, gameSelected, status FROM tables;"
        )
    return {
        row["tableid"]: {"game": row["gameselected"], "status": row["status"]}
        for row in rows
    }


async def getManagerHome(tableId: str):
    # return queue data and players currently playing with bets
    async with conn_pool.acquire() as conn:
        queue = await conn.fetch(
            """SELECT u.username AS username
               FROM users u
               JOIN queue q ON q.userid = u.id
               WHERE q.tableId = $1
               ORDER BY q.timeOfJoin ASC;""",
            tableId
        )
        activePlayers = await conn.fetch(
            """SELECT u.username AS username, ap.betAmount AS bet
               FROM users u
               JOIN activePlayers ap ON ap.userId = u.id
               WHERE ap.tableId = $1;""",
            tableId
        )

    return {
        "queue": _convertQueue(queue),
        "players": _convertActivePlayers(activePlayers)
    }




async def confirmPlayers(tablenum: str):
    # updated confirm players to consider players already seated, 
    # new logic -> slots left(how many to pick) = max_players - playersinqreadytojoin - playersalreadyseated
    async with conn_pool.acquire() as conn:
        await conn.execute(
            """UPDATE queue q
                SET readytojoin = TRUE
                WHERE q.number IN (
            SELECT q2.number
            FROM queue q2
            JOIN tables t ON q2.tableid = t.tableid
            WHERE q2.tableid = $1
                AND q2.readytojoin = FALSE
            ORDER BY q2.timeofjoin ASC
            LIMIT (
                SELECT GREATEST(0, t2.max_players - COUNT(DISTINCT q3.userid) - COUNT(DISTINCT ap.userid))
                FROM tables t2
                LEFT JOIN queue q3 ON q3.tableid = t2.tableid AND q3.readytojoin = TRUE
                LEFT JOIN activeplayers ap ON ap.tableid = t2.tableid
                WHERE t2.tableid = $1)
            );""",tablenum
        )


async def getTableConfiguration(tableId: str):
    async with conn_pool.acquire() as conn:
        configuration = await conn.fetchrow(
            """SELECT gameSelected AS game, max_players AS maxPlayers
               FROM tables WHERE tableId = $1;""",
            tableId
        )
    if not configuration:
        raise DbError(f"Table {tableId} not found")
    return {
        "game": configuration["game"],
        "maxPlayers": configuration["maxplayers"]
    }


async def flushTable(tableId: str):
    async with conn_pool.acquire() as conn:
        status = await conn.execute(
            "DELETE FROM activePlayers WHERE tableId = $1;", tableId
        )
    if status.endswith("0"):
        raise DbError(f"Could not flush table {tableId}")
    return {"status": "ok"}


async def removeFromQueue(username: str, tablenum: str):
    async with conn_pool.acquire() as conn:
        row = await conn.execute(
            """DELETE FROM queue q
               USING users u
               WHERE q.userId = u.id
                 AND u.username = $1
                 AND q.tableId = $2;""",
            username, tablenum
        )
        if not row.endswith("1"):
            raise DbError(f"Could not delete {username} from table {tablenum}")
    return {"status": "ok"}


async def removeFromGame(username: str, tablenum: str):
    async with conn_pool.acquire() as conn:
        try:
            async with conn.transaction():
                # refund bet back to balance
                await conn.execute(
                    """UPDATE accounts a
                       SET balance = balance + ap.betAmount
                       FROM activePlayers ap
                       JOIN users u ON u.id = ap.userId
                       WHERE a.user_id = ap.userId
                         AND u.username = $1
                         AND ap.tableId = $2;""",
                    username, tablenum
                )
                await conn.execute(
                    """DELETE FROM activePlayers ap
                       USING users u
                       WHERE ap.userId = u.id
                         AND u.username = $1
                         AND ap.tableId = $2;""",
                    username, tablenum
                )
        except Exception as e:
            raise DbError(f"Could not remove {username} from {tablenum}: {str(e)}")
    return {"status": "ok"}

async def getTableDetails(tableId: str):
# return  queue data, players currently playing, player bets, 
    async with conn_pool.acquire() as conn:
        queue = await conn.fetch(
            """SELECT u.username AS username FROM users u JOIN queue q 
            ON q.userId = u.id WHERE tableId = $1 ORDER BY q.timeOfJoin ASC;""", tableId
        )
        activePlayers = await conn.fetch(
            """
            SELECT u.username AS username, a.betAmount AS bet 
            FROM users u JOIN activePlayers a ON a.userid = u.id WHERE tableId = $1;
            """, tableId
        )
    
    playersCleaned = _convertActivePlayers(activePlayers)
    queueCleaned = _convertQueue(queue)

    return {
        "queue": queueCleaned,
        "players": playersCleaned
    }


async def getQueueAndActivePlayers(tableId):
    async with conn_pool.acquire() as conn:
        players_rows = await conn.fetch(
        """
        SELECT u.username, a.betamount
        FROM activeplayers a
        JOIN users u ON u.id = a.userid
        WHERE a.tableid = $1
        """,
        tableId
        )

        queue_rows = await conn.fetch(
        """
        SELECT q.number, u.username
        FROM queue q
        JOIN users u ON u.id = q.userid
        WHERE q.tableid = $1
        ORDER BY q.number ASC
        """,
        tableId
        )
    return {
        "players": { row["username"]: row["betamount"] for row in players_rows },
        "queue":   { str(row["number"]): row["username"] for row in queue_rows }
    }

#------------- Functions serving manager POST endpoints -------------#

async def setTableConfiguration(tablename: str, game: str, maxPlayers: int):
    async with conn_pool.acquire() as conn:
        response = await conn.execute(
            """UPDATE tables
               SET gameSelected = $1, max_players = $2
               WHERE tableId = $3;""",
            game, maxPlayers, tablename
        )
    if response.endswith("1"):
        return {"status": "ok"}
    else:
        return {"status": "fail"}

async def startGame(tablenum: str):
    async with conn_pool.acquire() as conn:
        response = await conn.execute(
            "UPDATE tables SET status = 'active' WHERE tableId = $1;", tablenum
        )
    if response.endswith("1"):
        return {"status": "ok"}
    else:
        raise DbError(f"Could not start game for table {tablenum}")


async def endGame(result: dict, tablenum: str):

    async with conn_pool.acquire() as conn:
        try:
            async with conn.transaction():

                # Step 1: Insert into gamesPlayed
                row = await conn.fetchrow(
                    """INSERT INTO gamesPlayed (game, tableId)
                       SELECT gameSelected, tableId
                       FROM tables
                       WHERE tableId = $1
                       RETURNING gameId, game;""",
                    tablenum
                )
                if row is None:
                    raise ValueError(f"No table found with tableId={tablenum}, INSERT returned nothing")

                game_id = row["gameid"]
                players = await conn.fetch(
                    """SELECT u.username, u.id, ap.betAmount
                       FROM activePlayers ap
                       JOIN users u ON u.id = ap.userId
                       WHERE ap.tableId = $1;""",
                    tablenum
                )

                if not players:
                    raise ValueError(f"No active players found for tableId={tablenum}, aborting endGame")

                # Step 3: Build update/log lists
                balance_updates = []
                logs = []
                for p in players:
                    username = p["username"]
                    user_id = p["id"]
                    initial = p["betamount"]  # asyncpg lowercases column names

                    if username not in result:
                        raise KeyError(f"Player '{username}' not found in result dict. result keys: {list(result.keys())}")

                    final_amount = result[username]
                    change = final_amount - initial
                    balance_updates.append((change, user_id))
                    logs.append((game_id, user_id, initial, final_amount))

                # Step 4: Update account balances
                await conn.executemany(
                    """UPDATE accounts
                       SET balance = balance + $1
                       WHERE user_id = $2;""",
                    balance_updates
                )

                # Step 5: Insert game player logs
                await conn.executemany(
                    """INSERT INTO gamePlayerLogs (gameId, userId, initialBet, finalAmount)
                       VALUES ($1, $2, $3, $4);""",
                    logs
                )

                # Step 6: Delete active players
                await conn.execute(
                    "DELETE FROM activePlayers WHERE tableId = $1;", tablenum
                )

                # Step 7: Reset table status
                await conn.execute(
                    "UPDATE tables SET status = 'idle' WHERE tableId = $1;", tablenum
                )

        except Exception as e:
            raise DbError(str(e)) from e
    return {"status": "ok"}
