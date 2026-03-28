import asyncpg
import asyncio
import os
from dotenv import load_dotenv
from passlib.hash import bcrypt
from exceptions import InvalidSession, dbError, couldNotGetUsernameAvailability, authenticationFailure

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


async def _getUsernameFromUuid(uuid) -> str:
    async with conn_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT username FROM users WHERE id = $1;", uuid
        )
        if not row:
            raise dbError("Internal db error - could not get corresponding username from uuid")
        return row["username"]

async def _getTeamnameFromUuid(uuid) -> str:
    async with conn_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT affiliation FROM users WHERE id = $1;", uuid
        )
        if not row:
            raise dbError("Internal db error - could not get corresponding teamname from uuid")
        return row["affiliation"]

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


async def checkUsernameAvailability(username: str):
    async with conn_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM users WHERE username = $1;", username
        )
    return {"available": not row}




async def getPlayerHome(session_token):
# return affiliated teamname, credits belonging to the user, total team credits, list of transactions and game logs

async def getManagerHome(session_token):
# return  queue data, players currently playing, player bets, 

async def getQueue(session_token)
# return json with game name and their current status in q, total q length










