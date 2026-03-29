from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import db_handler as db
from contextlib import asynccontextmanager
from pydantic import BaseModel
from exceptions import (
    InvalidSession, dbError, couldNotGetUsernameAvailability,
    authenticationFailure, transactionError
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_conn_pool_and_cleaner()
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="frontend"), name="static")
pages = Jinja2Templates(directory="frontend")


# ------------------ data models to validate request bodies ------------------#

class LoginCredentials(BaseModel):
    username: str
    password: str

class TransferDetail(BaseModel):
    recepient: str
    amount: int

class GameBet(BaseModel):
    tablenum: str
    amount: int

class ParticipationConfirm(BaseModel):
    tablenum: str
    confirmation: bool
    betAmount: str = "0"

class TableConfig(BaseModel):
    tablenum: str
    game: str = ""
    max_players: int = 6

class GameResults(BaseModel):
    tablenum: str
    results: dict                   # { player_uuid_str: final_amount }

class QueueJoin(BaseModel):
    tablenum: str

class ConfirmPlayers(BaseModel):
    tablenum: str
    numberOfPlayers: int


# ------------------ Internal helper ---------------------------#

def _redirect_login():
    return RedirectResponse(url="/login", status_code=303)


# ---------------------- middleware ----------------------------#

# All paths that require a valid player session
player_protected = [
    "/home", "/pay", "/payees", "/play",
    "/transfer", "/queue", "/gameConfirm",
    "/queue/join", "/queue/leave",          # queue sub-routes also need auth
]

# All paths that require a valid manager session
manager_protected = [
    "/table",
    "/table/configure",
    "/table/confirmPlayers",
    "/table/startGame",
    "/table/endGame",
    "/table/players",
]


@app.middleware("http")
async def validate_request(request: Request, call_next):
    session_token = request.cookies.get("session_token")
    path = request.url.path

    if path in player_protected:
        status = await db.validate(session_token=session_token, role="player")
        if not status:
            return _redirect_login()
        request.state.session_token = session_token
        return await call_next(request)

    elif path in manager_protected:
        status = await db.validate(session_token=session_token, role="manager")
        if not status:
            return _redirect_login()
        request.state.session_token = session_token
        return await call_next(request)

    else:
        request.state.session_token = session_token
        return await call_next(request)


# ---------------------- Custom Exception Handling -----------------------#

@app.exception_handler(InvalidSession)
async def invalid_session_handler(request: Request, exc: InvalidSession):
    return pages.TemplateResponse(
        request, "error.html", {"message": exc.message}, status_code=401
    )

@app.exception_handler(dbError)
async def db_error_handler(request: Request, exc: dbError):
    return pages.TemplateResponse(
        request, "error.html", {"message": exc.message}, status_code=500
    )

@app.exception_handler(couldNotGetUsernameAvailability)
async def username_availability_handler(request: Request, exc: couldNotGetUsernameAvailability):
    return pages.TemplateResponse(
        request, "error.html", {"message": "Could not check username availability."}, status_code=500
    )

@app.exception_handler(authenticationFailure)
async def auth_failure_handler(request: Request, exc: authenticationFailure):
    # 401 lets fetch()-based callers detect failure vs success
    return pages.TemplateResponse(
        request, "error.html", {"message": exc.message}, status_code=401
    )

@app.exception_handler(transactionError)
async def transaction_error_handler(request: Request, exc: transactionError):
    return pages.TemplateResponse(
        request, "error.html", {"message": exc.message}, status_code=400
    )


# ----------------------- GET endpoints --------------------#

@app.get("/")
async def landing(request: Request):
    return pages.TemplateResponse(request, "landing.html")


@app.get("/login")
async def login_page(request: Request):
    return pages.TemplateResponse(request, "login.html")


@app.get("/home")
async def get_user_landing(request: Request):
    session_token = request.state.session_token
    response = await db.getPlayerHome(session_token=session_token)
    return pages.TemplateResponse(
        request,
        "userhome.html",
        {
            "teamname": response["teamname"],
            "usercredits": response["usercredits"],
            "teamcredits": response["teamcredits"],
            "transactions": response["transactions"],
            "gamelogs": response["gamelogs"],
        },
    )


@app.get("/pay")
async def payment(request: Request, to: str = None):
    return pages.TemplateResponse(request, "pay.html", {"recipient": to})


@app.get("/payees")
async def payees(request: Request):
    session_token = request.state.session_token
    payee_list = await db.getPayees(session_token=session_token)
    return pages.TemplateResponse(request, "payees.html", {"payees": payee_list})


@app.get("/logout")
async def logout(request: Request):
    session_token = request.state.session_token
    if session_token:
        await db.deleteSessionToken(session_token=session_token)
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session_token")
    return response


@app.get("/play")
async def play(request: Request):
    session_token = request.state.session_token
    games_and_queue = await db.getUserQueue(session_token=session_token)
    return pages.TemplateResponse(request, "play.html", {"games_and_queue": games_and_queue})


@app.get("/table")
async def get_table(request: Request, tablenum: str = "1"):
    table = await db.getTableDetails(tablenum)
    return pages.TemplateResponse(
        request,
        "table.html",
        {
            "tablenum": tablenum,
            "queue": table["queue"],
            "players": table["players"],
        }
    )


@app.get("/queue")
async def get_queue(request: Request):
    session_token = request.state.session_token
    queue = await db.getUserQueue(session_token)
    return JSONResponse(queue)


@app.get("/gameConfirm")
async def check_participation(request: Request):
    session_token = request.state.session_token
    pending = await db.getParticipation(session_token)
    return pages.TemplateResponse(request, "gameconfirm.html", {"pending": pending})


# ------------------------ POST endpoints ----------------------#

@app.post("/login")
async def login_post(creds: LoginCredentials):
    session_token = await db.getSessionToken(
        username=creds.username, password=creds.password
    )
    # Return JSON — fetch() receives the Set-Cookie header directly on a 200
    # response, so the browser stores the cookie before we navigate to /home.
    # A RedirectResponse(303) would cause fetch() to silently drop the cookie.
    response = JSONResponse({"ok": True})
    response.set_cookie(
        key="session_token",
        value=str(session_token),
        httponly=True,
        samesite="lax",
    )
    return response


@app.post("/transfer")
async def transfer_post(request: Request, details: TransferDetail):
    session_token = request.state.session_token
    await db.transfer(session_token, details.recepient, details.amount)
    # Return JSON so the fetch()-based pay.html can handle it inline
    return JSONResponse({"ok": True, "message": f"Successfully sent {details.amount} credits to {details.recepient}."})


@app.post("/queue/join")
async def join_queue(request: Request, body: QueueJoin):
    session_token = request.state.session_token
    await db.insertIntoQueue(session_token=session_token, tablenum=body.tablenum)
    return JSONResponse({"status": "joined", "tablenum": body.tablenum})


@app.post("/queue/leave")
async def leave_queue(request: Request, body: QueueJoin):
    session_token = request.state.session_token
    user_uuid = await db._uuidFromSession(session_token)
    async with db.conn_pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM queue WHERE userid = $1 AND tableid = $2;",
            user_uuid, int(body.tablenum)
        )
    return JSONResponse({"status": "left"})


@app.post("/gameConfirm")
async def confirm_participation(request: Request, participation: ParticipationConfirm):
    session_token = request.state.session_token
    await db.confirmParticipation(
        session_token=session_token,
        tablenum=participation.tablenum,
        confirmation=participation.confirmation,
        betAmount=participation.betAmount,
    )
    # Return JSON — the frontend uses fetch() and checks res.ok, then navigates
    return JSONResponse({"ok": True})


@app.post("/game")
async def play_post(request: Request, details: GameBet):
    session_token = request.state.session_token
    await db.insertIntoQueue(session_token=session_token, tablenum=details.tablenum)
    return JSONResponse({"ok": True, "message": f"You've joined the queue for table {details.tablenum}. Good luck!"})


# ----------------------- Manager-only endpoints -------------------#

@app.get("/table/players")
async def get_table_players(request: Request, tablenum: str = "1"):
    """Returns {uuid: username} for active players — used by end-game UI."""
    players = await db.getActivePlayers(tablenum)
    return JSONResponse(players)


@app.post("/table/configure")
async def configure_table(request: Request, config: TableConfig):
    if config.game:
        await db.setGameForTable(tablenum=config.tablenum, game=config.game)
    await db.setMaxPlayersForTable(tablenum=config.tablenum, max_players=config.max_players)
    return JSONResponse({"status": "configured"})


@app.post("/table/confirmPlayers")
async def confirm_players(request: Request, body: ConfirmPlayers):
    selected = await db.confirmPlayers(
        numberOfPlayers=body.numberOfPlayers, tablenum=body.tablenum
    )
    return JSONResponse({"status": "notified", "selectedPlayers": selected})


@app.post("/table/startGame")
async def start_game(request: Request, body: QueueJoin):
    async with db.conn_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT userid FROM activeplayers WHERE tableid = $1;", int(body.tablenum)
        )
    players = [str(r["userid"]) for r in rows]
    if not players:
        raise dbError("No confirmed players for this table")
    game_id = await db.startGame(players=players, tablenum=body.tablenum)
    return JSONResponse({"status": "started", "gameId": game_id})


@app.post("/table/endGame")
async def end_game(request: Request, body: GameResults):
    await db.endGame(results=body.results, tablenum=body.tablenum)
    return JSONResponse({"status": "ended"})
