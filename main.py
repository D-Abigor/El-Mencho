from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import db_handler
from contextlib import asynccontextmanager
from pydantic import BaseModel

  
app = FastAPI(lifespan=lifespan)
pages = Jinja2Templates(directory="frontend")


@asynccontextmanager
def lifespan(app: FastAPI):
    DB_Handler.init_conn_pool_and_cleaner()
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


  


#------------------ Internal helper function ---------------------------#

def _redirect_login():
    return RedirectResponse(url="/login", status_code=303)
  

#------------------------ middleware ----------------------------#
protected = ["/home", "/pay", "/payees", "/play", "/transfer", "/table"]


@app.middleware("http")
async def validate_request(request: Request, call_next):
  session_token = request.cookies.get("session_token")
  if request.url.path in protected:
    status = await db_handler.validate(token = session_token, "user")
    if status:
      response = await call_next(request)
      request.state.session_token = session_token
      return response
    else:
      raise InvalidSession()
  else:
    response = await call_next(request)
  


#----------------------- custom exceptions ------------------#

class InvalidSession(Exception):
  pass

class payee_list_unobtainable(Exception):
  pass


#----------------------Custom Exception Handling -----------------------#

@app.exception_handler(InvalidSession)
async def validation_exception_handler(request: Request):
    return pages.TemplateResponse("error.html", {"message":" invalid session, kindly login"})

@app.exception_handler(payee_list_ubobtainable)
async def validation_exception_handler(request: Request):
    return pages.TemplateResponse("error.html", {"message":" could not obtain payee list"})


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
  status, package = await DB_Handler.get_user_landing(request.state.session_token)
  
  if not status:
      return pages.TemplateResponse(
          "error.html", {"request": request, "message": package}
      )
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
    return pages.TemplateResponse(
        "pay.html", {"request": request, "recipient": to}
    )


@app.get("/payees")
async def payees(request: Request):
  session_token = request.state.session_token
  status, payee_list = await DB_Handler.get_payees(session_token)
  if not status:
      raise payee_list_unobtainable()
  return pages.TemplateResponse(
      "payees.html", {"request": request, "payees": payee_list}
  )


@app.get("/logout")
async def logout(request: Request):
    session_token = request.state.session_token
    if session_id:
        await DB_Handler.delete_session_id(session_token)
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session_token")
    return response



@app.get("/play")


@app.get("/availability")


@app.get("/table")

@app.get("/queue")


#------------------------ POST endpoints ----------------------#
@app.post("/login")
async def login_post(creds: login, response: Response):


@app.post("/transfer")
async def transfer_post(details: transferDetail, response: Response):

@app.post("/game)
async def play_post(details: game, response: Response):





















