import asyncpg
import asyncio
import os
from dotenv import load_dotenv
from passlib.hash import bcrypt
from exceptions import InvalidSession, dbError, couldNotGetUsernameAvailability, authenticationFailure, transactionError

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

  
#----------------- Internal Helper ----------------------#

async def _getuuid(username: str) -> str:
    async with conn_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM users WHERE username = $1;", username
        )
        if not row:
            raise dbError("Internal db error - could not get corresponding uuid for your username")
        return str(row["id"])


async def _uuidFromSession(session_token: str) -> str:
    async with conn_pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT user_id FROM sessions
               WHERE session_token = $1 AND expires_at > NOW();""",
            session_token,
        )
        if not row:
            raise dbError("Internal db error - could not get corresponding uuid")
        return row["user_id"]


async def _getUsernameFromUuid(uuid: str) -> str:
    async with conn_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT username FROM users WHERE id = $1;", uuid
        )
        if not row:
            raise dbError("Internal db error - could not get corresponding username from uuid")
        return row["username"]

async def _getTeamnameFromUuid(uuid: str) -> str:
    async with conn_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT affiliation FROM users WHERE id = $1;", uuid
        )
        if not row:
            raise dbError("Internal db error - could not get corresponding teamname from uuid")
        return row["affiliation"]

def _gameLogstoDescriptive(gamelogs: list[asyncpg.Record]):
    cleanedLogs = []
    for entries in gamelogs:
        game = entries["game"]
        time = entries["timeOfFinish"]
        creditChange = entries["finalAmount"] - entries["initial_bet"]
        if creditChange >= 0:
            creditChange = abs(creditChange)
            line = f"you played {game} at {time} and won {creditChange}"
        else:
            creditChange = abs(creditChange)
            line = f"you played {game} at {time} and lost {creditChange}"
        cleanedLogs.append(line)
    return cleanedLogs
    
def _transactionstoDescriptive(transactionlogs: list([asyncpg.Record]), uuid: str):
    cleanedLogs = []
    for entries in cleanedLogs:
        change = entries["change"]
        source = entries["source"]
        destination = entries["destination"]
        if source == uuid:
            line = f"you sent {destination} {change}"
        elif destination == uuid:
            line = f"{source} sent you {change}"
        cleanedLogs.append(line)
    return cleanedLogs

def _convertQueue(queue: list([asyncpg.Record])):
    queuecleaned = {}
    index = 1
    for players in queue:
        queuecleaned[index] = players[username]
        index+=1
    return queuecleaned

def _convertActivePlayers(activePlayers: list([asyncpg.Record])):
    players = {}
    for player in activePlayers:
        players[player.username] = player.bet
    return players

def _cleanUserQueue(activeQueue: list([asyncpg.Record])):
    queues = {}
    for queue in activeQueue:
        queues[queue["game"]] = queue["position"]
    return queues 


#------------------------ route helper functions ------------------------#

async def validate(session_token: str, role: str) -> bool:
    async with conn_pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT u.access
               FROM sessions s
               JOIN users u ON s.user_id = u.id
               WHERE s.session_token = $1 AND s.expires_at > NOW();""",
            session_token,
        )
    return bool(row and row["access"] == role)

async def getPayees(session_token: str):
    source_uuid = await _uuid_from_session(session_token)          # if time allows improve this by comverting to single query using join
    teamname = await _getTeamnameFromUuid(source_uuid)
    async with conn_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT username FROM users WHERE id != $1 AND affiliation = $2 ORDER BY username;",
            source_uuid, teamname
        )
    if not rows:
        raise dbError(f"Internal db error - could not get list of payees affiliatied to {teamname}")
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
            raise dbError("Internal db error - user does not exist")


async def deleteSessionToken(session_token: str):
    async with conn_pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM sessions WHERE session_token = $1;", session_token
        )
async def transfer(session_id: str, destination_username: str, amount):
    # valdiating transfer amount
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        raise transactionError("Amount must be a whole number")
    if amount <= 0:
        raise transactionError("Amount must be greater than zero")

    source_uuid = await _uuid_from_session(session_id)
    dest_uuid = await _getuuid(destination_username)

    if str(source_uuid) == str(dest_uuid):
        raise transactionError("Cannot transfer to yourself")

    async with conn_pool.acquire() as conn:
        try:
            async with conn.transaction():
                # Lock both rows in a consistent UUID order to prevent deadlock
                ids = sorted([str(source_uuid), str(dest_uuid)])
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
                    return transactionError("Insufficient balance")

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
            raise transactionError(f"Transaction failed: {str(e)}")

async def getPlayerHome(session_token):
# return affiliated teamname, credits belonging to the user, total team credits, list of transactions and game logs
    userid = _getuuid(session_token)
    async with conn_pool.acquire() as conn:
        # combine queries into 1 if time allows
        userDetails = await conn.fetchrow(
            """SELECT u.affiliation AS teamname, a.balance AS userCredits 
            FROM users u JOIN accounts a ON u.id = a.user_id 
            WHERE u.id = $1;""", userid
        )
        generalDetails = await conn.fetchrow(
          """SELECT sum(a.balance) AS teamCredits
            FROM users u JOIN accounts a ON u.id = a.user_id 
            WHERE u.affiliation = $1;""", userDetails["teamname"]
        )
        gameLogs = await conn.fetch(
            """"SELECT b.game, b.timeOfFinish, a.initialBet, a.finalAmount 
            FROM gamePlayers a JOIN gamesPlayed b ON a.gameId = b.gameId 
            WHERE user_id = $1
            ORDER BY b.timeOfFinish DESC;""", userid
        )
        transactions = await conn.fetch(
            """SELECT t.change AS change, t.source AS source, t.destination AS destination 
            FROM transactions t WHERE t.source = $1 OR t.destination = $1"""
        )
    convertedTransactions = _transactionstoDescriptive(transactions, userid)
    convertedLogs = _gameLogstoDescriptive(gameLogs)
    return {
        "teamname": userDetails["teamname"],
        "usercredits": userDetails["userCredits"],
        "teamcredits": generalDetails["teamCredits"],
        "transactions": convertedTransactions,
        "gamelogs": convertedLogs 
        }

async def getManagerHome(session_token: str, game: str):
# return  queue data, players currently playing, player bets, 
    async with conn_pool.acquire() as conn:
        queue = conn.fetch(
            """SELECT u.username AS username FROM users u JOIN queue q 
            ON q.user_id = u.id ORDER BY q.timeOfJoin ASC;"""
        )
        activePlayers = conn.fetch(
            """
            SELECT u.username AS username a.betAmount AS bet 
            FROM users u JOIN activeGames a ON a.user_id = u.id WHERE game = $1;
            """, game
        )
    
    playersCleaned = _convertActivePlayers(activePlayers)
    queueCleaned = _convertQueue(queue)

    return {
        "queue": queueCleaned,
        "players": playersCleaned
    }

async def getUserQueue(session_token):
# return json with game name and their current status in q, total q length
    async with conn_pool.acquire() as conn:
        activeQueues = conn.fetch("""
        SELECT game, position FROM ( 
        SELECT game, ROW_NUMBER() OVER (
        PARTITION BY game
        ORDER BY timeOfJoin ASC) AS position
        FROM queue) q WHERE user_id = $1
        """, _uuid_from_session(session_token)
        )
    cleanedUserQueue = _cleanUserQueue(activeQueues)
    return cleanedUserQueue





async def removeFromQueue(username: str, game: str):
    uuid = _getuuid(username)
    async with conn_pool.acquire() as conn:
        row = conn.execute("DELETE FROM queue WHERE user_id = $1 AND game = $2 ;", uuid, game)




