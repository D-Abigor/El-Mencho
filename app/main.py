from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import db_handler as db
from contextlib import asynccontextmanager
from pydantic import BaseModel
from errors import InvalidSession, DbError, CouldNotGetUsernameAvailability, AuthenticationFailure, TransactionError
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

class amountBody(BaseModel):
    amount: int


#------------------ Internal helper ---------------------------#

def _redirect_login():
    return RedirectResponse(url="/login", status_code=303)

def error_response(request: Request, message: str):
    return RedirectResponse(url=f"/error?message={message}", status_code=303)
#------------------------ Middleware ----------------------------#

protected = ["/home", "/pay", "/payees", "/play", "/transfer", "/queue", "/gameConfirm"]

@app.middleware("http")
async def validate_request(request: Request, call_next):
    session_token = request.cookies.get("session_token")
    path = request.url.path

    if path in protected:
        status = await db.validate(session_token=session_token, role="player")
        if not status:
            return pages.TemplateResponse(
                "error.html",
                {"request": request, "message": "Invalid or expired session"},
                status_code=401
            )

    elif path == "/tables" or path.startswith("/table/"):
        status = await db.validate(session_token=session_token, role="manager")
        if not status:
            return pages.TemplateResponse(
                "error.html",
                {"request": request, "message": "Invalid or expired session"},
                status_code=401
            )
    elif path == "/players" or path.startswith("/table/"):
        status = await db.validate(session_token=session_token, role="minigamemanager")
        if not status:
            return pages.TemplateResponse(
                "error.html",
                {"request": request, "message": "Invalid or expired session"},
                status_code=401
            )

    request.state.session_token = session_token
    try:
        response = await call_next(request)
    except Exception as e:
        raise e
    return response

#---------------------- Exception Handlers -----------------------#

@app.exception_handler(InvalidSession)
async def invalid_session_handler(request: Request, exc: InvalidSession):
    return pages.TemplateResponse("error.html", {"request": request, "message": exc.message})

@app.exception_handler(DbError)
async def db_error_handler(request: Request, exc: DbError):
    return pages.TemplateResponse("error.html", {"request": request, "message": exc.message})

@app.exception_handler(CouldNotGetUsernameAvailability)
async def username_availability_handler(request: Request, exc: CouldNotGetUsernameAvailability):
    return pages.TemplateResponse("error.html", {"request": request, "message": "Could not check if username is available."})

@app.exception_handler(AuthenticationFailure)
async def auth_failure_handler(request: Request, exc: AuthenticationFailure):
    return pages.TemplateResponse("error.html", {"request": request, "message": exc.message})

@app.exception_handler(TransactionError)
async def transaction_error_handler(request: Request, exc: TransactionError):
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

@app.get("/error")
async def error_page(request: Request, message: str = "An error occurred."):
    return pages.TemplateResponse("error.html", {"request": request, "message": message})

#----------------------- GET endpoints — Player --------------------#

@app.get("/home")
async def get_user_landing(request: Request):
    session_token = request.state.session_token
    response = await db.getPlayerHome(session_token=session_token)
    print(response)
    return pages.TemplateResponse(
        "userhome.html",
        {
            "request": request,
            "username": response["username"],
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
    try:
        payeeList = await db.getPayees(session_token=session_token)
    except DbError as e:
        return error_response(request, e.message)
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
    try:
        session_token = await db.getSessionToken(
            username=creds.username, password=creds.password
        )
    except AuthenticationFailure as e:
        return error_response(request, e.message)
    except DbError as e:
        return error_response(request, e.message)

    if session_token:
        access = await db.getAccess(session_token)
        if access == 'player':
            redirect = RedirectResponse(url="/home", status_code=303)
        elif access == 'manager':
            redirect = RedirectResponse(url="/tables", status_code=303)
        else:
            redirect = RedirectResponse(url="/players", status_code=303)
        redirect.set_cookie(
            key="session_token",
            value=str(session_token),
            httponly=True,
            samesite="lax",
            secure=True
        )
        return redirect

@app.post("/transfer")
async def transfer_post(details: transferDetail, request: Request):
    session_token = request.state.session_token
    try:
        await db.transfer(session_token, details.recepient, details.amount)
    except TransactionError as e:
        return error_response(request, e.message)
    return pages.TemplateResponse(
        "successful_transaction.html",
        {"request": request, "message": f"Successfully transferred {details.amount} credits to {details.recepient}."}
    )

@app.post("/gameConfirm")
async def confirmParticipation(request: Request, participation: participationConfirm):
    print("game confirmation recieved as ", participation.confirmation)
    session_token = request.state.session_token
    try:
        await db.confirmParticipation(
            session_token=session_token,
            tablenum=participation.tablenum,
            confirmation=participation.confirmation,
            betAmount="350"
        )
    except TransactionError as e:
        return error_response(request, e.message)
    except DbError as e:
        return error_response(request, e.message)
    return RedirectResponse(url="/play", status_code=303)

@app.post("/play")
async def addtoQueue(request: Request, tablenum: enterQueue):
    session_token = request.state.session_token
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

#endpoint serving queue and active players for tableId
@app.get("/table/{tableId}/data")
async def getTableDetails(request: Request, tableId: str):
    details = await db.getTableDetails(tableId=tableId)
    return JSONResponse(details)




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
    status = await db.endGame(result=result.results, tablenum=tableId)
    return JSONResponse(status)


#-------------------- GET endpoint for minigame manager -------------#

@app.get("/players")
async def getPlayers(request: Request):
    try:
        players = await db.getAllPlayers()
    except DbError as e:
        return error_response(request,e.message)
    return pages.TemplateResponse("players.html", {"request": request, "players":players})

@app.get("/player/{username}")
async def playerProfile(request: Request, username: str):
    return pages.TemplateResponse(
        "player.html",
        {"request": request, "username": username},
    )
 
@app.get("/player/{username}/deduct")
async def getDeductPage(request: Request, username: str):
    return pages.TemplateResponse("deduct.html", {"request": request, "username": username})

@app.get("/player/{username}/add")
async def getAddPage(request: Request, username: str):
    return pages.TemplateResponse("add.html", {"request": request, "username": username})

#-------------------- POST endpoint for minigame manager --------------#

@app.post("/player/{username}/deduct")
async def deduct(request: Request, username: str, amount: amountBody):
    try:
        status = await db.deductFromUser(username = username, amount = amount.amount)
    except TransactionError as e:
        return JSONResponse({"error": e.message}, status_code=400)
    return JSONResponse({"status": "ok"})

@app.post("/player/{username}/add")
async def add(request: Request, username: str, amount: amountBody):
    try:
        status = await db.addToUser(username = username, amount= amount.amount)
    except TransactionError as e:
        return JSONResponse({"error": e.message}, status_code=400)
    return JSONResponse({"status": "ok"})
    
