import os
from datetime import date
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

class DatabaseManager:
    
    def __init__(self):
        url: str = os.getenv("SUPABASE_URL")
        key: str = os.getenv("SUPABASE_KEY")
        self.supabase: Client = create_client(url, key)

    # ==========================================
    # USUARIOS, LÍMITES Y STRIPE
    # ==========================================
    def create_user(self, email: str, password: str) -> dict:
        try:
            response = self.supabase.auth.sign_up({
                "email": email,
                "password": password
            })
            
            if response.user:
                # Intentamos recuperarlo de tu tabla pública
                user_data = self.get_user_by_email(email)
                
                if user_data:
                    return user_data
                else:
                    # El Auth funcionó, pero la BBDD pública no tiene el dato
                    raise Exception("Auth exitoso, pero no aparece en public.users. ¿Usaste la service_role key en el .env? ¿Se ejecutó bien el Trigger SQL?")
            
            raise Exception("Supabase no devolvió el User. ¿Tienes desactivada la confirmación por email en los ajustes?")
            
        except Exception as e:
            # Pasamos el error real hacia arriba
            raise Exception(f"Fallo detallado: {str(e)}")

    def verify_login(self, email: str, password: str) -> dict:
        try:
            # Supabase Auth validates the credentials
            response = self.supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            
            if response.user:
                return self.get_user_by_email(email)
            return False
        except Exception as e:
            # Usually means invalid credentials
            return False

    def get_user_by_email(self, email: str) -> dict:
        try:
            response = self.supabase.table("users").select("*").eq("email", email).execute()
            return response.data[0] if response.data else None
        except Exception:
            return None

    def update_stripe_data(self, user_id: str, customer_id: str, sub_id: str, status: str, plan: str) -> bool:
        try:
            self.supabase.table("users").update({
                "stripe_customer_id": customer_id,
                "stripe_subscription_id": sub_id,
                "stripe_subscription_status": status,
                "plan": plan
            }).eq("id", user_id).execute() # <-- AHORA BUSCAMOS POR ID
            return True
        except Exception:
            return False

    def check_compilation_limit(self, user_id: str) -> int:
        """Comprueba, actualiza los límites diarios y devuelve el conteo actual."""
        user = self.supabase.table("users").select("plan, daily_compilations, last_compilation_date").eq("id", user_id).execute().data[0]
        
        if not user.data:
            raise PermissionError("User not found in database.")

        if user['plan'] in ['premium', 'unlimited']:
            return 0 # Sin límites
            
        today_str = date.today().isoformat()
        
        # Si es un nuevo día, reseteamos el contador
        if str(user.get('last_compilation_date')) != today_str:
            self.supabase.table("users").update({
                "daily_compilations": 1, 
                "last_compilation_date": today_str
            }).eq("id", user_id).execute()
            return 1
            
        # Si es el mismo día, comprobamos el límite
        if user.get('daily_compilations', 0) >= 5:
            raise PermissionError("Plan Free: You have reached your daily limit of 5 AI compilations.")
            
        # Si no ha llegado al límite, incrementamos
        new_count = user.get('daily_compilations', 0) + 1
        self.supabase.table("users").update({
            "daily_compilations": new_count
        }).eq("id", user_id).execute()
        
        return new_count

    # ==========================================
    # GESTIÓN DE ARCHIVOS (Sin proyectos)
    # ==========================================
    def create_file(self, user_id: str, filename: str, pseudocode: str = "", item_type: str = "file", parent_id: str = None) -> dict:
        # 1. Actualizar si ya existe (buscamos por filename y parent_id para no sobreescribir archivos con el mismo nombre en distintas carpetas)
        query = self.supabase.table("files").select("id").eq("user_id", user_id).eq("filename", filename)
        if parent_id:
            query = query.eq("parent_id", parent_id)
        else:
            query = query.is_("parent_id", "null")
            
        existing = query.execute().data
        
        if existing:
            response = self.supabase.table("files").update({"pseudocode": pseudocode}).eq("id", existing[0]["id"]).execute()
            return response.data[0]

        # 2. Validar límites de usuarios Free al crear cosas nuevas
        user_response = self.supabase.table("users").select("plan").eq("id", user_id).execute()
        plan = user_response.data[0]["plan"]

        if plan == "free":
            if item_type == "folder":
                raise PermissionError("Plan Free: Folders are a Premium feature.")
            if item_type == "file" and len(pseudocode.split('\n')) > 10:
                raise PermissionError("Plan Free: Your code exceeds the 10 lines limit.")
                
            # Solo contamos archivos (no carpetas) para el límite de 3
            existing_files = self.supabase.table("files").select("id").eq("user_id", user_id).eq("item_type", "file").execute().data
            if item_type == "file" and len(existing_files) >= 3:
                raise PermissionError("Plan Free: You can only have 3 files maximum.")

        try:
            data_to_insert = {
                "user_id": user_id,
                "filename": filename,
                "pseudocode": pseudocode,
                "item_type": item_type,
                "parent_id": parent_id
            }
            response = self.supabase.table("files").insert(data_to_insert).execute()
            return response.data[0]
        except Exception as e:
            return None

    def update_file_translation(self, file_id: str, translated_code: str) -> dict:
        try:
            response = self.supabase.table("files").update({"translated_code": translated_code}).eq("id", file_id).execute()
            return response.data[0]
        except Exception:
            return None

    def get_files_by_user(self, user_id: str) -> list:
        try:
            response = self.supabase.table("files").select("*").eq("user_id", user_id).execute()
            return response.data
        except Exception:
            return []
            
    def delete_file(self, file_id: str) -> bool:
        try:
            self.supabase.table("files").delete().eq("id", file_id).execute()
            return True
        except Exception:
            return False

    def rename_file(self, file_id: str, new_name: str) -> bool:
        try:
            self.supabase.table("files").update({"filename": new_name}).eq("id", file_id).execute()
            return True
        except Exception:
            return False