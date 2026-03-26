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
  amount: int          # inter team transaction, amount restricted to be integers

class game(BaseModel):
  amount: int          # only integer bet amounts allowed

class gameQStatus(BaseModel):
  in_queue: bool
  position: int
  queue_length: int

class username_availability(BaseModel):
  available: bool




#------------------ Internal helper function ---------------------------#

def _redirect_login():
    return RedirectResponse(url="/login", status_code=303)
  

#------------------------ middleware ----------------------------#
protected = ["/home", "/pay", "/payees", "/play", "/transfer", "/table"]


@app.middleware("http")
async def validate_request(request: Request, call_next):
  session_token = request.cookies.get("session_token")
  if request.url.path in protected:
    status = await db.validate(session_token = session_token, role = "user")
    if status:
      response = await call_next(request)
      request.state.session_token = session_token
      return response
    else:
      raise InvalidSession()
  else:
    response = await call_next(request)
  

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
  package = await db.get_user_landing(session_token = session_token)
  return pages.TemplateResponse(
      "userhome.html",
      {
          "request": request,
          "balance": package["balance"],
          "transactions": package["transactions"],
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
  payee_list = await db.get_payees(session_token=session_token)
  return pages.TemplateResponse(
      "payees.html", {"request": request, "payees": payee_list}
  )


@app.get("/logout")
async def logout(request: Request):
    session_token = request.state.session_token
    if session_id:
        await db.delete_session_id(session_token = session_token)
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session_token")
    return response



@app.get("/play")
async def play(request: Request):
  session_token = request.state.session_token
  games_and_queue = await db.get_games_and_queue(session_token = session_token)
  response = pages.TemplateResponse(
    "play.html", {"request": request, "games_and_queue": games_and_queue}
  )
  return response



@app.get("/availability")
async def play(username: str = None):
  response = db.check_username_availability(username=username)
  return JSONResponse(response)
  
  

@app.get("/table")
async def get_table(request: Request, )

@app.get("/queue")


#------------------------ POST endpoints ----------------------#

@app.post("/login")
async def login_post(creds: login, response: Response):
  username = creds.username
  password = creds.password
  session_token = await db.get_session_token(
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
      session_id, data.get("destination", ""), data.get("amount")
  )
  return pages.TemplateResponse(
      "successful_transaction.html", {"request": request, "message": message}
  )


@app.post("/game)
async def play_post(details: game, response: Response):





















