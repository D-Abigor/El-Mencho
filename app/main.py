from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import db_handler as db
from contextlib import asynccontextmanager
from pydantic import BaseModel
from exceptions import InvalidSession, dbError, couldNotGetUsernameAvailability, authenticationFailure, transactionError
from fastapi.staticfiles import StaticFiles

@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_conn_pool_and_cleaner()
    yield

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="frontend"), name="static")
pages = Jinja2Templates(directory="frontend")


#------------------ Data models ------------------#

class cookie(BaseModel):
    session_token: str

class login(BaseModel):
    username: str
    password: str

class transferDetail(BaseModel):
    recepient: str
    amount: int

class participationConfirm(BaseModel):
    tablenum: str
    confirmation: bool
    betAmount: str

class tableConfig(BaseModel):
    tablenum: str
    game: str
    maxPlayers: int

class gameResults(BaseModel):
    tablenum: str
    results: dict           # { player_username: final_amount }

class playerPullDetails(BaseModel):
    tableId: str

class removeFromQueueDetails(BaseModel):
    tableId: str
    username: str

class tableNum(BaseModel):
    tableId: str

class enterQueue(BaseModel):
    tablenum: str


#------------------ Internal helper ---------------------------#

def _redirect_login():
    return RedirectResponse(url="/login", status_code=303)


#------------------------ Middleware ----------------------------#

protected = ["/home", "/pay", "/payees", "/play", "/transfer", "/queue", "/gameConfirm"]

@app.middleware("http")
async def validate_request(request: Request, call_next):
    session_token = request.cookies.get("session_token")
    print("Session token", session_token)
    path = request.url.path

    if path in protected:
        print("path detected as protected")
        status = await db.validate(session_token=session_token, role="player")
        if not status:
            return pages.TemplateResponse(
                "error.html",
                {"request": request, "message": "Invalid or expired session"},
                status_code=401
            )

    elif path == "/tables" or path.startswith("/table/"):
        print("path detected as manager level")
        # FIX: /tables (manager overview) was not covered by path.startswith("/table/")
        # FIX: /table/{tableId}/start was missing from the old managerEndpoints list
        status = await db.validate(session_token=session_token, role="manager")
        if not status:
            return pages.TemplateResponse(
                "error.html",
                {"request": request, "message": "Invalid or expired session"},
                status_code=401
            )

    request.state.session_token = session_token
    response = await call_next(request)
    return response

#---------------------- Exception Handlers -----------------------#

@app.exception_handler(InvalidSession)
async def invalid_session_handler(request: Request, exc: InvalidSession):
    return pages.TemplateResponse("error.html", {"request": request, "message": exc.message})

@app.exception_handler(dbError)
async def db_error_handler(request: Request, exc: dbError):
    return pages.TemplateResponse("error.html", {"request": request, "message": exc.message})

@app.exception_handler(couldNotGetUsernameAvailability)
async def username_availability_handler(request: Request, exc: couldNotGetUsernameAvailability):
    return pages.TemplateResponse("error.html", {"request": request, "message": "Could not check if username is available."})

@app.exception_handler(authenticationFailure)
async def auth_failure_handler(request: Request, exc: authenticationFailure):
    return pages.TemplateResponse("error.html", {"request": request, "message": exc.message})

@app.exception_handler(transactionError)
async def transaction_error_handler(request: Request, exc: transactionError):
    return pages.TemplateResponse("error.html", {"request": request, "message": exc.message})


#----------------------- GET endpoints — Public --------------------#

@app.get("/")
async def landing(request: Request):
    return pages.TemplateResponse("landing.html", {"request": request})

@app.get("/login")
async def login_get(request: Request):
    return pages.TemplateResponse("login.html", {"request": request})

@app.get("/leaderBoard")
async def getLeaderBoard(request: Request):
    leaderboard = await db.getLeaderBoard()
    return pages.TemplateResponse("leaderboard.html", {"request": request, "leaderboard": leaderboard})


#----------------------- GET endpoints — Player --------------------#

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
            "gamelogs": response["gamelogs"]
        },
    )

@app.get("/pay")
async def payment(request: Request, to: str = None):
    return pages.TemplateResponse("pay.html", {"request": request, "recipient": to})

@app.get("/payees")
async def payees(request: Request):
    session_token = request.state.session_token
    payeeList = await db.getPayees(session_token=session_token)
    return pages.TemplateResponse("payees.html", {"request": request, "payees": payeeList})

@app.get("/logout")
async def logout(request: Request):
    session_token = request.cookies.get("session_token")
    if session_token:
        await db.deleteSessionToken(session_token=session_token)
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session_token")
    return response

@app.get("/play")
async def play(request: Request):
    session_token = request.state.session_token
    games_and_queue = await db.getUserQueue(session_token=session_token)
    print(games_and_queue)
    return pages.TemplateResponse(
        "play.html",
        {
            "request": request,
            "games_and_queue": games_and_queue,
        }
    )

@app.get("/queue")
async def getqueue(request: Request):
    session_token = request.state.session_token
    queue = await db.getUserQueue(session_token)
    return JSONResponse(queue)

@app.get("/gameConfirm")
async def checkParticipation(request: Request):
    session_token = request.state.session_token
    queueStatus = await db.getParticipation(session_token)
    return JSONResponse(queueStatus)

#------------------------ POST endpoints — Player ----------------------#

@app.post("/login")
async def login_post(creds: login, request: Request):
    print("receieved post at /login")
    session_token = await db.getSessionToken(
        username=creds.username, password=creds.password
    )
    print("session_token from login", session_token)
    redirect = RedirectResponse(url="/home", status_code=303)
    redirect.set_cookie(
        key="session_token",
        value=str(session_token),
        httponly=True,
        samesite="lax",
    )
    return redirect

@app.post("/transfer")
async def transfer_post(details: transferDetail, request: Request):
    session_token = request.state.session_token
    await db.transfer(session_token, details.recepient, details.amount)
    # FIX: db.transfer returns True (bool) on success, not a message string.
    # Substituting a fixed success message here instead of passing the bool to the template.
    return pages.TemplateResponse(
        "successful_transaction.html",
        {"request": request, "message": f"Successfully transferred {details.amount} credits to {details.recepient}."}
    )

@app.post("/gameConfirm")
async def confirmParticipation(request: Request, participation: participationConfirm):
    session_token = request.state.session_token
    await db.confirmParticipation(
        session_token=session_token,
        tablenum=participation.tablenum,
        confirmation=participation.confirmation,
        betAmount=participation.betAmount
    )
    return RedirectResponse(url="/play", status_code=303)

@app.post("/play")
async def addtoQueue(request: Request, tablenum: enterQueue):
    session_token = request.state.session_token
    print("recieved player insert into queue post with details:", tablenum)
    status = await db.insertIntoQueue(session_token, tablenum.tablenum)


#--------------------- GET endpoints — Manager -----------------#

@app.get("/tables")
async def getTablesForManager(request: Request):
    tables = await db.getTablesForManager()
    return pages.TemplateResponse("tables.html", {"request": request, "details": tables})

@app.get("/table/{tableId}")
async def getTableDetails(request: Request, tableId: str):
    details = await db.getTableDetails(tableId=tableId)
    return pages.TemplateResponse("table.html", {"request": request, "details": details})

@app.get("/table/{tableId}/pull")
async def pullPlayers(request: Request, tableId: str):
    await db.confirmPlayers(tablenum=tableId)
    return JSONResponse({"status": "ok"})

@app.get("/table/{tableId}/configure")
async def getTableConfiguration(request: Request, tableId: str):
    details = await db.getTableConfiguration(tableId=tableId)
    return pages.TemplateResponse("tableConfiguration.html", {"request": request, "details": details})

@app.get("/table/{tableId}/flush")
async def flushTable(request: Request, tableId: str):
    status = await db.flushTable(tableId=tableId)
    return JSONResponse(status)

@app.get("/table/{tableId}/remove")
async def removeFromGame(request: Request, tableId: str, removePlayer: str = None):
    if not removePlayer:
        raise HTTPException(status_code=400, detail="removePlayer query param required")
    status = await db.removeFromGame(username=removePlayer, tablenum=tableId)
    return JSONResponse(status)

@app.get("/table/{tableId}/queue")
async def removeFromQueue(request: Request, tableId: str, removePlayer: str = None):
    if not removePlayer:
        raise HTTPException(status_code=400, detail="removePlayer query param required")
    status = await db.removeFromQueue(username=removePlayer, tablenum=tableId)
    return JSONResponse(status)


#-------------------- POST endpoints — Manager -----------------#

@app.post("/table/{tableId}/config")
async def configureTable(request: Request, tableId: str, configuration: tableConfig):
    status = await db.setTableConfiguration(
        tablename=configuration.tablenum,
        game=configuration.game,
        maxPlayers=configuration.maxPlayers
    )
    return JSONResponse(status)

@app.post("/table/{tableId}/start")
async def startGame(request: Request, tableId: str):
    status = await db.startGame(tablenum=tableId)
    return JSONResponse(status)

@app.post("/table/{tableId}/end")
async def endGame(request: Request, tableId: str, result: gameResults):
    # FIX: use tableId from the URL as the authoritative table identifier,
    # not result.tablenum from the request body which could disagree with the URL.
    status = await db.endGame(result=result.results, tablenum=tableId)
    return JSONResponse(status)
