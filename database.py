import os
from supabase import create_client, Client
from dotenv import load_dotenv

import os
import bcrypt
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

class DatabaseManager:
    
    def __init__(self):
        url: str = os.getenv("SUPABASE_URL")
        key: str = os.getenv("SUPABASE_KEY")
        self.supabase: Client = create_client(url, key)

    # ==========================================
    # USUARIOS Y STRIPE
    # ==========================================
    def create_user(self, email: str, password: str) -> dict:
        try:
            # Encrypt the password before saving it to the database
            salt = bcrypt.gensalt()
            hashed_pw = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
            
            response = self.supabase.table("users").insert(
                {
                    "email": email,
                    "password_hash": hashed_pw,
                    "plan": "free"
                }
            ).execute()
            
            return response.data[0]
        except Exception as e:
            print(f"[ERROR] Creating user: {e}")
            return None

    def get_user_by_email(self, email: str) -> dict:
        try:
            response = self.supabase.table("users").select("*").eq("email", email).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"[ERROR] Getting user: {e}")
            return None

    def verify_login(self, email: str, password: str) -> dict:
        """Checks if the user exists and verifies the bcrypt password hash."""
        user = self.get_user_by_email(email)
        if not user:
            return None  # User does not exist
            
        stored_hash = user.get("password_hash")
        if not stored_hash:
            return False # Legacy user without password
            
        # Verify the provided password against the stored hash
        if bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8')):
            return user
        else:
            return False # Wrong password

    def update_stripe_data(self, email: str, customer_id: str, sub_id: str, status: str, plan: str) -> bool:
        try:
            self.supabase.table("users").update(
                {
                    "stripe_customer_id": customer_id,
                    "stripe_subscription_id": sub_id,
                    "stripe_subscription_status": status,
                    "plan": plan
                }
            ).eq("email", email).execute()
            return True
        except Exception as e:
            print(f"[ERROR] Updating Stripe data: {e}")
            return False

    # ==========================================
    # PROYECTOS
    # ==========================================
    def create_project(self, user_id: str, name: str) -> dict:
        # Validar plan antes de crear
        user_response = self.supabase.table("users").select("plan").eq("id", user_id).execute()
        if not user_response.data:
            raise ValueError("Usuario no encontrado.")
            
        plan = user_response.data[0]["plan"]
        
        if plan == "free":
            projects_data = self.supabase.table("projects").select("id").eq("user_id", user_id).execute().data
            if projects_data:
                project_ids = [p["id"] for p in projects_data]
                files_data = self.supabase.table("files").select("id").in_("project_id", project_ids).execute().data
                if len(files_data) >= 3:
                    raise PermissionError("Plan Free: Has alcanzado el limite de 3 ficheros totales en tu cuenta.")

        try:
            response = self.supabase.table("projects").insert(
                {"user_id": user_id, "name": name}
            ).execute()
            return response.data[0]
        except Exception as e:
            print(f"[ERROR] Creando proyecto: {e}")
            return None

    def get_projects_by_user(self, user_id: str) -> list:
        try:
            response = self.supabase.table("projects").select("*").eq("user_id", user_id).execute()
            return response.data
        except Exception as e:
            print(f"Error obteniendo proyectos: {e}")
            return []

    # ==========================================
    # ARCHIVOS (Con validacion de lineas y proyectos multiples)
    # ==========================================
    def create_file(self, user_id: str, project_id: str, filename: str, pseudocode: str = "") -> dict:
        # 0. Si el usuario le vuelve a dar a "Ejecutar", actualizamos el archivo existente
        existing_file = self.supabase.table("files").select("id").eq("project_id", project_id).eq("filename", filename).execute().data
        if existing_file:
            response = self.supabase.table("files").update({"pseudocode": pseudocode}).eq("id", existing_file[0]["id"]).execute()
            return response.data[0]

        # 1. Validar limites del usuario (para archivos nuevos)
        user_response = self.supabase.table("users").select("plan").eq("id", user_id).execute()
        if not user_response.data:
            raise ValueError("Usuario no encontrado en la base de datos.")
            
        plan = user_response.data[0]["plan"]

        if plan == "free":
            num_lineas = len(pseudocode.split('\n'))
            if num_lineas > 50:
                raise PermissionError(f"Plan Free: Tu codigo tiene {num_lineas} lineas. El limite es 50.")
                
            existing_files = self.supabase.table("files").select("id").eq("project_id", project_id).execute().data
            if len(existing_files) >= 1:
                raise PermissionError("Plan Free: No puedes tener mas de 1 fichero por proyecto.")

        try:
            response = self.supabase.table("files").insert(
                {
                    "project_id": project_id,
                    "filename": filename,
                    "pseudocode": pseudocode
                }
            ).execute()
            return response.data[0]
        except Exception as e:
            print(f"[ERROR] Creando archivo: {e}")
            return None

    def update_file_translation(self, file_id: str, translated_code: str, ai_language: str) -> dict:
        try:
            response = self.supabase.table("files").update(
                {
                    "translated_code": translated_code,
                    "ai_language": ai_language
                }
            ).eq("id", file_id).execute()
            return response.data[0]
        except Exception as e:
            print(f"[ERROR] Actualizando traduccion: {e}")
            return None

    def get_files_by_project(self, project_id: str) -> list:
        try:
            response = self.supabase.table("files").select("*").eq("project_id", project_id).execute()
            return response.data
        except Exception as e:
            print(f"Error obteniendo archivos: {e}")
            return []
        
    def delete_file(self, file_id: str) -> bool:
        try:
            self.supabase.table("files").delete().eq("id", file_id).execute()
            return True
        except Exception as e:
            print(f"[ERROR] Eliminando archivo: {e}")
            return False

    def rename_file(self, file_id: str, new_name: str) -> bool:
        try:
            self.supabase.table("files").update({"filename": new_name}).eq("id", file_id).execute()
            return True
        except Exception as e:
            print(f"[ERROR] Renombrando archivo: {e}")
            return False