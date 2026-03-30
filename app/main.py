from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import db_handler as db
from contextlib import asynccontextmanager
from pydantic import BaseModel
from exceptions import InvalidSession, dbError, couldNotGetUsernameAvailability

  
@asynccontextmanager
def lifespan(app: FastAPI):
    db.init_conn_pool_and_cleaner()
    yield

app = FastAPI(lifespan=lifespan)
pages = Jinja2Templates(directory="frontend")
 

  
#------------------ data models to validate response ------------------#

class cookie(BaseModel):
  session_token: str

class login(BaseModel):
  username: str
  password: str

class transferDetail(BaseModel):
  recepient: str
  amount: int          # transaction, amount restricted to be integers

class game(BaseModel):
  amount: int          # only integer bet amounts allowed

class participationConfirm(BaseModel):
  game: str
  confirmation: bool

class tableConfig(BaseModel):
  tablenum: str
  game: str
  maxPlayers: str

class gameResults(BaseModel):
    tablenum: str
    results: dict                   # { player_username: final_amount }
  
class playerPullDetails(BaseModel):
  tableId: str

class removeFromQueueDetails(BaseModel):
  tableId: str
  username: str


class tableNum(BaseModel):
  tableId: str
#------------------ Internal helper function ---------------------------#

def _redirect_login():
    return RedirectResponse(url="/login", status_code=303)
  

#------------------------ middleware ----------------------------#
protected = ["/home", "/pay", "/payees", "/play", "/transfer"]
managerEndpoints = [
  "/tables",
  "/table/{tableId}",
  "/table/{tableId}/pull",
  "/table/{tableId}/configure",
  "/table/{tableId}/flush",
  "/table/{tableId}/config",
  "/table/{tableId}/end",
  "/queue/{tableId}/remove",
  "/queue/{tableId}/queue"
]


@app.middleware("http")
async def validate_request(request: Request, call_next):
  session_token = request.cookies.get("session_token")
  if request.url.path in protected:
    status = await db.validate(session_token = session_token, role = "player")
    if status:
      response = await call_next(request)
      request.state.session_token = session_token
      return response
    else:
      raise InvalidSession()
  elif request.url.path == "/table":
    status = await db.validate(session_token = session_token, role = "manager")
    if status:
      response = await call_next(request)
      request.state.session_token = session_token
      return response
  else:
    response = await call_next(request)
    return response
  

#----------------------Custom Exception Handling -----------------------#

@app.exception_handler(InvalidSession)
def validation_exception_handler(request: Request, exc: Exception):
    return pages.TemplateResponse("error.html", {"request": request, "message":exc.message})

@app.exception_handler(dbError)
def payee_list_exception_handler(request: Request, exc: Exception):
    return pages.TemplateResponse("error.html", {"request": request, "message":exc.message})

@app.exception_handler(couldNotGetUsernameAvailability)
def username_availability_exception_handler(request: Request, exc: Exception):
  return pages.TemplateResponse("error.html", {"request": request, "message":" could not check if username is available."})

@app.exception_handler(authenticationFailure)
def username_availability_exception_handler(request: Request, exc: Exception):
  return pages.TemplateResponse("error.html", {"request": request, "message":exc.message})

@app.exception_handler(transactionError)
def username_availability_exception_handler(request: Request, exc: Exception):
  return pages.TemplateResponse("error.html", {"request": request, "message":exc.message})
#----------------------- GET endpoints FOR player--------------------#


@app.get("/leaderBoard")
async def getLeaderBoard(request: Request):
  return pages.TemplateResponse("leaderboard.html", {"request": request, "leaderboard": leaderboard})


  
@app.get("/")
async def landing(request: Request):
    return pages.TemplateResponse("landing.html", {"request": request})


@app.get("/login")
async def login(request: Request):
    return pages.TemplateResponse("login.html", {"request": request})


@app.get("/home")
async def get_user_landing(request: Request):
  session_token = request.state.session_token
  response = await db.getPlayerHome(session_token = session_token)
  return pages.TemplateResponse(
      "userhome.html",
      {
          "request": request,
          "teamname": response["teamname"],
          "teamcredits": response["teamcredits"],
          "transactions": response["transactions"],
          "gamelogs": response["gamelogs"]
      },
  )


@app.get("/pay")
async def payment(request: Request, to: str = None):
  response = pages.TemplateResponse(
        "pay.html", {"request": request, "recipient": to}
    )
  return response

@app.get("/payees")
async def payees(request: Request):
  session_token = request.state.session_token
  payeeList = await db.getPayees(session_token=session_token)
  return pages.TemplateResponse(
      "payees.html", {"request": request, "payees": payeeList}
  )


@app.get("/logout")
async def logout(request: Request):
    session_token = request.state.session_token
    if session_id:
        await db.deleteSessionToken(session_token = session_token)
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session_token")
    return response



@app.get("/queue")
async def play(request: Request):
  session_token = request.state.session_token
  games_and_queue = await db.getUserQueue(session_token = session_token)
  response = pages.TemplateResponse(
    "play.html", 
    {
      "request": request,
      "games_and_queue": games_and_queue,

    }
  )
  return response


@app.get("/queue")
async def getqueue(request: Request):
  session_token = request.state.session_token
  queue = await db.getUserQueue(session_token)
  return JSONResponse(queue)

@app.get("/gameConfirm")
async def checkParticipation(request: Request):
  session_token = request.state.session_token
  queueStatus = await db.getParticipation(session_token)

@app.get("/game")

#------------------------ POST endpoints for players----------------------#
#rewrite
@app.post("/gameConfirm")
async def confirmParticipation(request: Request, participation: participationConfirm):
  session_token = request.state.session_token
  confirm = await db.confirmParticipation(session_token = session_token, game = participation.game, confirmation = participation.confirmation)
  redirect = RedirectResponse(url="/game", status_code = 202)
  return redirect




@app.post("/login")
async def login_post(creds: login, request: Request):
  username = creds.username
  password = creds.password
  session_token = await db.getSessionToken(
        username=username,password=password
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
async def transfer_post(details: transferDetail, request: Request):
  session_id = request.state.session_token
  message = await db.transfer(
      session_id, details.recepient, details.amount
  )
  return pages.TemplateResponse(
      "successful_transaction.html", {"request": request, "message": message}
  )


@app.post("/game") # post that decides how much to bet
async def play_post(details: game, response: Response):

#-----------------GET FOR MANAGERS -----------------#

@app.get("/tables")
async def getTablesForManager(request: Request):
  tables = await db.getTableDetails()
  response = pages.TemplateResponse("tables.html", {"request": request, "details":tables})
  return response

# table.html needs to poll table/{tableId} every x seconds to update quueue and player details excluding the manager input 
@app.get("/table/{tableId}")
async def getTableDetails(request: Request):
  details = await db.getTableDetails(tableId = tableId)
  response = pages.TemplateResponse("table.html", {"request": request, "details": details})
  return response


@app.get("/table/{tableId}/pull")
async def pullPlayers(request: Request, pullDetails: playerPullDetails):
  status = await db.confirmPlayers( tablenum=tableId)
  


@app.get("/table/{tableId}/configure")
async def getTableConfiguration(request: Request):
  details = await db.getTableConfiguration(tableId = tableID)
  response = pages.TemplateResponse("tableConfiguration.html", {"request": request, "details": details})
  return response

@app.get("/table/{tableId}/flush")
async def flushTable(request: Request, tablenum: Tablenum):
  tableId = tablenum.tableId
  status  = db.flushTable(tableId = tableID)
  return JSONResponse(status)

# remove player from game table
@app.get("/table/{tableId}/remove")
async def removeFromQueue(request: Request, removePlayer: str = None):
  status = await db.removeFromGame(username = removePlayer, tablenum = tableId)
  return JSONResponse(status)

# remove player from queue
@app.get("/table{tableId}/queue")
async def removeFromQueue(request: Request, removePlayer: str = None):
  status = await db.removeFromQueue(username = removePlayer, tablenum = tableId)
  return JSONResponse(status)



#----------------POST FOR MANAGERS -----------------#


@app.post("/table/{tableId}/config")
async def configureTable(request: Request, configuration: tableConfig):
  tablename = configuration.tablename
  game = configuration.game
  maxPlayers = configuration.maxPlayers
  status = await db.setTableConfiguration(tablename = tablename, game = game, maxPlayers=maxPlayers)
  return JSONResponse(status)


@app.post("/table/{tableId}/end")
async def configureTable(request: Request, result: gameResults):
  tablenum = result.tablenum
  result = result.results
  status = await db.endGame(tablenum = tablenum, result = result )
  return JSONResponse(status)












