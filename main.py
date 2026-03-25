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

class register(BaseModel):
  username: str
  password: str


#------------------ Internal helper function ---------------------------#

def _redirect_login():
    return RedirectResponse(url="/login", status_code=303)
  

#------------------------ middleware ----------------------------#
protected = ["/home", "/pay", "/payees"]


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
      raise InvalidSession
  else:
    response = await call_next(request)
  


#----------------------- custom exceptions ------------------#

class InvalidSession(Exception):
  pass


#----------------------Custom Exception Handling -----------------------#

@app.exception_handler(InvalidSession)
async def validation_exception_handler(request: Request):
    return pages.TemplateResponse("error.html", {"message":" invalid session, kindly login"})

#----------------------- GET endpoints --------------------#

@app.get("/")
async def landing(request: Request):
    return pages.TemplateResponse("landing.html", {"request": request})


@app.get("/login")
async def login(request: Request):
    return pages.TemplateResponse("login.html", {"request": request})


@app.get("/register")
async def register(request: Request):
    return pages.TemplateResponse("register.html", {"request": request})


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


























