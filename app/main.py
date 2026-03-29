from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import db_handler as db
from contextlib import asynccontextmanager
from pydantic import BaseModel
from exceptions import InvalidSession, dbError, couldNotGetUsernameAvailability

  
app = FastAPI(lifespan=lifespan)
pages = Jinja2Templates(directory="frontend")
 

@asynccontextmanager
def lifespan(app: FastAPI):
    db.init_conn_pool_and_cleaner()
    yield
  
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



#------------------ Internal helper function ---------------------------#

def _redirect_login():
    return RedirectResponse(url="/login", status_code=303)
  

#------------------------ middleware ----------------------------#
protected = ["/home", "/pay", "/payees", "/play", "/transfer"]



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
#----------------------- GET endpoints --------------------#

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



@app.get("/play")
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

@app.get("/table")
async def getTables(request: Request, game: str = None):
  game  = await db.getManagerHome(game)
  response = pages.TemplateResponse(
    "table.html",
    {
      "request": request,
      "queue": game["queue"],
      "players": game["players"]
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

#------------------------ POST endpoints ----------------------#

@app.post("/gameConfirm")
async def confirmParticipation(request: Request, participation: participationConfirm):
  session_token = request.state.session_token
  confirm = await db.confirmParticipation(session_token = session_token, game = participation.game, confirmation = participation.confirmation)
  redirect = RedirectResponse(url="/game", status_code = 202)
  return redirect




@app.post("/login")
async def login_post(creds: login, response: Response):
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
async def transfer_post(details: transferDetail, response: Response):
  session_id = request.state.session_token
  message = await db.transfer(
      session_id, details.recepient, details.amount
  )
  return pages.TemplateResponse(
      "successful_transaction.html", {"request": request, "message": message}
  )


@app.post("/game") # post that decides how much to bet
async def play_post(details: game, response: Response):





















