import os
import stripe
from dotenv import load_dotenv

load_dotenv()

class StripeManager:
    
    def __init__(self):
        stripe.api_key = os.getenv("STRIPE_API_KEY")
        self.webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
        self.premium_price_id = os.getenv("STRIPE_PRICE_ID")
        self.domain_url = os.getenv("DOMAIN_URL", "http://localhost:8000")

    def create_checkout_session(self, user_email: str, user_id: str, return_url: str = None) -> dict:
        try:
            # Aseguramos que la URL base es la correcta y le quitamos la barra final si la tiene
            base_url = return_url if return_url else self.domain_url
            base_url = base_url.rstrip('/')

            # FORZAMOS a que vuelva a la raíz (index.html) para que Vercel no de 404
            success_url = f"{base_url}?session_id={{CHECKOUT_SESSION_ID}}"
            cancel_url = f"{base_url}/"

            session = stripe.checkout.Session.create(
                customer_email = user_email,
                client_reference_id = user_id,
                payment_method_types = ["card"],
                line_items = [{"price": self.premium_price_id, "quantity": 1}],
                mode = "subscription",
                success_url = success_url,
                cancel_url = cancel_url,
            )
            return {"status": "success", "url": session.url, "session_id": session.id}
            
        except Exception as e:
            print(f"[ERROR] Creando sesion de pago Stripe: {e}")
            return {"status": "error", "url": None, "session_id": None}

    def get_checkout_session(self, session_id: str):
        """Recupera los datos de una sesión de pago directamente de Stripe."""
        try:
            return stripe.checkout.Session.retrieve(session_id)
        except Exception as e:
            print(f"[ERROR] Recuperando sesión: {e}")
            return None

    def create_customer_portal(self, customer_id: str, return_url: str = None) -> str:
        try:
            base_url = return_url if return_url else self.domain_url
            base_url = base_url.rstrip('/')
            
            session = stripe.billing_portal.Session.create(
                customer = customer_id,
                return_url = base_url
            )
            return session.url
        except Exception as e:
            return None

    def verify_webhook(self, payload: bytes, sig_header: str):
        try:
            return stripe.Webhook.construct_event(payload=payload, sig_header=sig_header, secret=self.webhook_secret)
        except stripe.error.SignatureVerificationError:
            return None
        except ValueError:
            return None
        
    def cancel_subscription_immediately(self, sub_id: str):
        """Fuerza la cancelación inmediata en Stripe para evitar reintentos de cobro."""
        try:
            stripe.Subscription.delete(sub_id)
        except Exception as e:
            print(f"[ERROR STRIPE] Cancelando suscripción {sub_id}: {e}")