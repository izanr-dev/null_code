from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from database import DatabaseManager
from external import AICompiler
from stripe_manager import StripeManager

# Inicializamos los modulos
db = DatabaseManager()
ai = AICompiler()
pagos = StripeManager()

app = FastAPI(title="NL2Exec Core API")

# Configuracion CORS (Permite que el frontend se comunique con esta API)
app.add_middleware(
    CORSMiddleware,
    allow_origins = ["*"], # En produccion, pondremos el dominio de tu frontend
    allow_credentials = True,
    allow_methods = ["*"],
    allow_headers = ["*"],
)

# ==========================================
# RUTAS DE ESTADO
# ==========================================
@app.get("/")
def read_root():
    return \
    {
        "status": "online",
        "service": "NL2Exec API"
    }

# ==========================================
# RUTAS DE GESTION (USUARIOS Y PROYECTOS)
# ==========================================
@app.post("/api/users")
async def register_user(request: Request):
    """Crea o devuelve un usuario existente."""
    data = await request.json()
    email = data.get("email")
    
    if not email:
        raise HTTPException(status_code=400, detail="Email requerido.")
        
    user = db.get_user_by_email(email)
    if not user:
        user = db.create_user(email)
        
    return user

@app.post("/api/projects")
async def create_new_project(request: Request):
    """Crea un proyecto para un usuario."""
    data = await request.json()
    user_id = data.get("user_id")
    name = data.get("name")
    
    if not user_id or not name:
        raise HTTPException(status_code=400, detail="user_id y name son requeridos.")
        
    try:
        project = db.create_project(user_id=user_id, name=name)
        return project
    except Exception as e:
        raise HTTPException(status_code=403, detail=str(e))
    
    # --- NUEVAS RUTAS DE AUTENTICACION REAL ---
    # --- NUEVAS RUTAS DE AUTENTICACION REAL ---
@app.post("/api/auth/login")
async def login_user(request: Request):
    data = await request.json()
    email = data.get("email")
    password = data.get("password")
    
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required.")
        
    user = db.get_user_by_email(email)
    if not user:
        # 404 triggers the frontend to switch to the Sign Up screen
        raise HTTPException(status_code=404, detail="Account not found. Please create one.")
        
    valid_user = db.verify_login(email, password)
    if valid_user is False:
        raise HTTPException(status_code=401, detail="Invalid password.")
        
    return valid_user

@app.post("/api/auth/signup")
async def signup_user(request: Request):
    data = await request.json()
    email = data.get("email")
    password = data.get("password")
    
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required.")
        
    if db.get_user_by_email(email):
        raise HTTPException(status_code=400, detail="Email already registered. Please Login.")
        
    user = db.create_user(email, password)
    if not user:
        raise HTTPException(status_code=500, detail="Error creating account.")
    return user

@app.delete("/api/files/{file_id}")
async def delete_file(file_id: str):
    success = db.delete_file(file_id)
    if not success: raise HTTPException(status_code=500, detail="Error deleting file")
    return {"status": "success"}

@app.put("/api/files/{file_id}")
async def rename_file(file_id: str, request: Request):
    data = await request.json()
    success = db.rename_file(file_id, data.get("new_name"))
    if not success: raise HTTPException(status_code=500, detail="Error renaming file")
    return {"status": "success"}

# ==========================================
# RUTAS DEL COMPILADOR IA
# ==========================================
@app.post("/api/compile")
async def compile_code(request: Request):
    """
    Recibe el pseudocodigo del frontend, valida los limites del usuario,
    lo compila con la IA y guarda el resultado.
    """
    try:
        data = await request.json()
        user_id = data.get("user_id")
        project_id = data.get("project_id")
        filename = data.get("filename")
        pseudocode = data.get("pseudocode")

        if not all([user_id, project_id, filename, pseudocode]):
            raise HTTPException(status_code=400, detail="Faltan parametros requeridos.")

        # 1. Guardar el archivo en la BBDD (Aqui se aplican las restricciones del modelo de negocio)
        try:
            file_record = db.create_file(
                user_id = user_id,
                project_id = project_id,
                filename = filename,
                pseudocode = pseudocode
            )
        except PermissionError as pe:
            raise HTTPException(status_code=403, detail=str(pe))

        # 2. Enviar a la IA (DeepSeek)
        ia_response = ai.compile_pseudocode(pseudocode)

        # 3. Procesar respuesta y actualizar base de datos si fue exitoso
        if ia_response.get("status") == "success":
            db.update_file_translation(
                file_id = file_record["id"],
                translated_code = ia_response.get("code"),
                ai_language = "python" 
            )

        return ia_response

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# RUTAS DE FACTURACION (STRIPE)
# ==========================================
@app.post("/api/checkout")
async def create_checkout(request: Request):
    """Genera la URL de pago de Stripe."""
    data = await request.json()
    user_email = data.get("email")
    user_id = data.get("user_id")

    if not user_email or not user_id:
         raise HTTPException(status_code=400, detail="Email y user_id son requeridos.")

    session_data = pagos.create_checkout_session(user_email, user_id)
    
    if session_data["status"] == "success":
        return {"url": session_data["url"]}
    else:
        raise HTTPException(status_code=500, detail="Error creando sesion de pago.")

@app.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    """Stripe llama a esta ruta silenciosamente cuando un pago tiene exito."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not sig_header:
        raise HTTPException(status_code=400, detail="Falta la firma de Stripe.")

    event = pagos.verify_webhook(payload, sig_header)
    
    if event is None:
        raise HTTPException(status_code=400, detail="Firma de Webhook invalida.")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        
        customer_email = session.get("customer_details", {}).get("email")
        customer_id = session.get("customer")
        subscription_id = session.get("subscription")
        user_id = session.get("client_reference_id") 

        print(f"[INFO] Webhook: Pago exitoso recibido para usuario ID: {user_id}")

        if user_id:
            exito = db.update_stripe_data(
                email = customer_email,
                customer_id = customer_id,
                sub_id = subscription_id,
                status = "active",
                plan = "premium"
            )
            
            if exito:
                print(f"[EXITO] BBDD actualizada: Usuario {customer_email} es ahora Premium.")
            else:
                print(f"[ERROR] Webhook recibio el pago pero fallo al actualizar la BBDD.")

    return JSONResponse(status_code=200, content={"status": "success"})