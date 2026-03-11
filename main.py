from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from database import DatabaseManager
from external import AICompiler
from stripe_manager import StripeManager

db = DatabaseManager()
ai = AICompiler()
pagos = StripeManager()

app = FastAPI(title="NullCode API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
    return response

@app.get("/")
def read_root():
    return {"status": "online"}

# --- AUTH ---
@app.post("/api/auth/login")
async def login_user(request: Request):
    data = await request.json()
    email, password = data.get("email"), data.get("password")
    
    if not email or not password: 
        raise HTTPException(400, "Email and password are required.")
        
    user = db.verify_login(email, password)
    if not user: 
        raise HTTPException(401, "Invalid email or password.")
        
    return user

@app.post("/api/auth/signup")
async def signup_user(request: Request):
    data = await request.json()
    email, password = data.get("email"), data.get("password")
    
    if not email or not password: 
        raise HTTPException(400, "Email and password are required.")
    
    try:
        # Registramos al usuario en Supabase Auth
        db.supabase.auth.sign_up({
            "email": email,
            "password": password
        })
        # Devolvemos solo un mensaje de éxito, no iniciamos sesión
        return {"status": "success", "message": "Please verify your email."}
    except Exception as e:
        raise HTTPException(400, str(e))

# --- ARCHIVOS ---
@app.delete("/api/files/{file_id}")
async def delete_file(file_id: str):
    if not db.delete_file(file_id): raise HTTPException(500, "Error deleting file")
    return {"status": "success"}

@app.put("/api/files/{file_id}")
async def rename_file(file_id: str, request: Request):
    data = await request.json()
    if not db.rename_file(file_id, data.get("new_name")): raise HTTPException(500, "Error renaming file")
    return {"status": "success"}

@app.get("/api/files/{user_id}")
async def get_user_files(user_id: str):
    try:
        files = db.get_files_by_user(user_id)
        return {"status": "success", "files": files}
    except Exception as e:
        raise HTTPException(500, "Error fetching files.")
    
@app.post("/api/files/save")
async def save_file_manual(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    filename = data.get("filename")
    pseudocode = data.get("pseudocode", "")
    item_type = data.get("item_type", "file")
    parent_id = data.get("parent_id") # Puede ser nulo
    
    if not user_id or not filename:
        raise HTTPException(400, "Missing user_id or filename")
        
    try:
        file_record = db.create_file(user_id=user_id, filename=filename, pseudocode=pseudocode, item_type=item_type, parent_id=parent_id)
        if not file_record:
            raise HTTPException(500, "Error saving file to cloud.")
            
        return {"status": "success", "file": file_record}
    except PermissionError as pe:
        raise HTTPException(403, str(pe))
    except Exception as e:
        raise HTTPException(500, str(e))

# --- COMPILADOR IA ---
@app.post("/api/compile")
async def compile_code(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    filename = data.get("filename")
    pseudocode = data.get("pseudocode")
    item_type = data.get("item_type", "file") 
    parent_id = data.get("parent_id")        

    if not all([user_id, filename, pseudocode]):
        raise HTTPException(400, "Missing parameters.")

    try:
        # 1. Comprobar limite de archivos / lineas y guardar
        file_record = db.create_file(user_id=user_id, filename=filename, pseudocode=pseudocode)
        
        # 2. Comprobar limite diario de compilaciones (IA) y obtener el uso actual
        current_uses = db.check_compilation_limit(user_id)
        
    except PermissionError as pe:
        raise HTTPException(403, str(pe))

    # 3. Traducir con IA
    ia_response = ai.compile_pseudocode(pseudocode)

    if ia_response.get("status") == "success":
        db.update_file_translation(file_id=file_record["id"], translated_code=ia_response.get("code"))

    # 4. Añadimos el contador al JSON de respuesta
    ia_response["daily_compilations"] = current_uses

    return ia_response

# --- STRIPE ---
@app.post("/api/checkout")
async def create_checkout(request: Request):
    data = await request.json()
    return_url = data.get("return_url") # La URL exacta donde esta el usuario
    session_data = pagos.create_checkout_session(data.get("email"), data.get("user_id"), return_url)
    
    if session_data["status"] == "success": 
        return {"url": session_data["url"]}
    raise HTTPException(500, "Error creating checkout session.")

@app.get("/api/verify-session/{session_id}")
async def verify_session(session_id: str):
    """El frontend llama a esta ruta tras volver de pagar para validar el pago en tiempo real."""
    session = pagos.get_checkout_session(session_id)
    
    # Usar .get() es a prueba de balas para objetos de Stripe
    if session and session.get("payment_status") == "paid":
        customer_id = session.get("customer")
        sub_id = session.get("subscription")
        user_id = session.get("client_reference_id") 
        
        if user_id:
            # Actualizamos la BBDD usando el user_id seguro
            db.update_stripe_data(user_id, customer_id, sub_id, "active", "premium")
            return {"status": "success", "plan": "premium"}
            
    return {"status": "pending"}

@app.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    event = pagos.verify_webhook(payload, sig_header)
    
    if event and event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session.get("client_reference_id")
        
        if user_id:
            db.update_stripe_data(
                user_id = user_id, # <-- Pasamos el user_id en lugar del email
                customer_id = session.get("customer"),
                sub_id = session.get("subscription"),
                status = "active", 
                plan = "premium"
            )
    return JSONResponse(status_code=200, content={"status": "success"})

@app.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    event = pagos.verify_webhook(payload, sig_header)
    
    if event and event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session.get("client_reference_id")
        if user_id:
            db.update_stripe_data(
                email = session.get("customer_details", {}).get("email"),
                customer_id = session.get("customer"),
                sub_id = session.get("subscription"),
                status = "active", plan = "premium"
            )
    return JSONResponse(status_code=200, content={"status": "success"})

@app.post("/api/billing")
async def billing_portal(request: Request):
    data = await request.json()
    user = db.get_user_by_email(data.get("email"))
    return_url = data.get("return_url") # Capturamos la URL exacta de Vercel
    
    if not user or not user.get("stripe_customer_id"):
        raise HTTPException(400, "No active subscription found.")
        
    portal_url = pagos.create_customer_portal(user["stripe_customer_id"], return_url)
    if portal_url: 
        return {"url": portal_url}
    raise HTTPException(500, "Error generating billing portal.")