from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import db_handler as db
from contextlib import asynccontextmanager
from pydantic import BaseModel
from exceptions import (
    InvalidSession, dbError, couldNotGetUsernameAvailability,
    authenticationFailure, transactionError                  # FIX: all imported
)


@asynccontextmanager                                          # FIX: defined before use
async def lifespan(app: FastAPI):
    await db.init_conn_pool_and_cleaner()                    # FIX: needs await
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
    results: dict                   # { player_uuid: final_amount }

class QueueJoin(BaseModel):
    tablenum: str

class ConfirmPlayers(BaseModel):
    tablenum: str
    numberOfPlayers: int


# ------------------ Internal helper ---------------------------#

def _redirect_login():
    return RedirectResponse(url="/login", status_code=303)


# ---------------------- middleware ----------------------------#

player_protected = ["/home", "/pay", "/payees", "/play", "/transfer", "/queue", "/gameConfirm"]
manager_protected = ["/table"]


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
        # Store token on state even for unprotected routes so handlers can read it
        request.state.session_token = session_token
        return await call_next(request)


# ---------------------- Custom Exception Handling -----------------------#

@app.exception_handler(InvalidSession)
async def invalid_session_handler(request: Request, exc: InvalidSession):
    return pages.TemplateResponse("error.html", {"request": request, "message": exc.message})

@app.exception_handler(dbError)
async def db_error_handler(request: Request, exc: dbError):
    return pages.TemplateResponse("error.html", {"request": request, "message": exc.message})

@app.exception_handler(couldNotGetUsernameAvailability)
async def username_availability_handler(request: Request, exc: couldNotGetUsernameAvailability):
    return pages.TemplateResponse("error.html", {"request": request, "message": "Could not check username availability."})

@app.exception_handler(authenticationFailure)
async def auth_failure_handler(request: Request, exc: authenticationFailure):
    return pages.TemplateResponse("error.html", {"request": request, "message": exc.message})

@app.exception_handler(transactionError)
async def transaction_error_handler(request: Request, exc: transactionError):
    return pages.TemplateResponse("error.html", {"request": request, "message": exc.message})


# ----------------------- GET endpoints --------------------#

@app.get("/")
async def landing(request: Request):
    return pages.TemplateResponse("landing.html", {"request": request})


@app.get("/login")
async def login_page(request: Request):
    return pages.TemplateResponse("login.html", {"request": request})


@app.get("/home")
async def get_user_landing(request: Request):
    session_token = request.state.session_token
    response = await db.getPlayerHome(session_token=session_token)
    return pages.TemplateResponse(
        "userhome.html",
        {
            "request": request,
            "teamname": response["teamname"],
            "usercredits": response["usercredits"],
            "teamcredits": response["teamcredits"],
            "transactions": response["transactions"],
            "gamelogs": response["gamelogs"],
        },
    )


@app.get("/pay")
async def payment(request: Request, to: str = None):
    return pages.TemplateResponse("pay.html", {"request": request, "recipient": to})


@app.get("/payees")
async def payees(request: Request):
    session_token = request.state.session_token
    payee_list = await db.getPayees(session_token=session_token)
    return pages.TemplateResponse(
        "payees.html", {"request": request, "payees": payee_list}
    )


@app.get("/logout")
async def logout(request: Request):
    session_token = request.state.session_token   # FIX: was session_id
    if session_token:
        await db.deleteSessionToken(session_token=session_token)
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session_token")
    return response


@app.get("/play")
async def play(request: Request):
    session_token = request.state.session_token
    games_and_queue = await db.getUserQueue(session_token=session_token)
    return pages.TemplateResponse(
        "play.html",
        {"request": request, "games_and_queue": games_and_queue}
    )


@app.get("/table")
async def get_table(request: Request, tablenum: str = "1"):
    table = await db.getTableDetails(tablenum)
    return pages.TemplateResponse(
        "table.html",
        {
            "request": request,
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
    return pages.TemplateResponse(
        "gameconfirm.html", {"request": request, "pending": pending}
    )


# ------------------------ POST endpoints ----------------------#

@app.post("/login")
async def login_post(creds: LoginCredentials):
    session_token = await db.getSessionToken(
        username=creds.username, password=creds.password
    )
    redirect = RedirectResponse(url="/home", status_code=303)
    redirect.set_cookie(
        key="session_token",
        value=str(session_token),
        httponly=True,
        samesite="lax",
    )
    return redirect


@app.post("/transfer")
async def transfer_post(request: Request, details: TransferDetail):
    session_id = request.state.session_token
    await db.transfer(session_id, details.recepient, details.amount)
    return pages.TemplateResponse(
        "success.html",
        {"request": request, "message": f"Successfully sent {details.amount} credits to {details.recepient}."}
    )


@app.post("/queue/join")
async def join_queue(request: Request, body: QueueJoin):
    session_token = request.state.session_token
    await db.insertIntoQueue(session_token=session_token, tablenum=body.tablenum)
    return JSONResponse({"status": "joined", "tablenum": body.tablenum})


@app.post("/queue/leave")
async def leave_queue(request: Request, body: QueueJoin):
    session_token = request.state.session_token
    username = await db._getUsernameFromUuid(await db._uuidFromSession(session_token))
    # leave all queues matching the table
    async with db.conn_pool.acquire() as conn:
        uuid = await db._uuidFromSession(session_token)
        await conn.execute(
            "DELETE FROM queue WHERE userid = $1 AND tableid = $2;",
            uuid, int(body.tablenum)
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
    if participation.confirmation:
        return RedirectResponse(url="/play", status_code=303)
    else:
        return RedirectResponse(url="/play", status_code=303)


@app.post("/game")
async def play_post(request: Request, details: GameBet):
    session_token = request.state.session_token
    await db.insertIntoQueue(session_token=session_token, tablenum=details.tablenum)
    return pages.TemplateResponse(
        "success.html",
        {"request": request, "message": f"You've joined the queue for table {details.tablenum}. Good luck!"}
    )


# ----------------------- Manager-only POST endpoints -------------------#

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
    # Fetch all confirmed active players for the table
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
