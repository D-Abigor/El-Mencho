import asyncpg
import asyncio
import os
from dotenv import load_dotenv
from passlib.hash import bcrypt
from exceptions import InvalidSession, dbError, couldNotGetUsernameAvailability

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
               WHERE session_id = $1 AND expires_at > NOW();""",
            session_token,
        )
        if not row:
            raise dbError("Internal db error - could not get corresponding uuid")
        return row["user_id"]'


async def _getUsernameFromUuid(uuid) -> str:
    async with conn_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT username FROM users WHERE id = $1;", uuid
        )
        if not row:
            raise dbError("Internal db error - could not get corresponding username from uuid")
        return row["username"]


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

































