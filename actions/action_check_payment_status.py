import aiohttp
from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.types import DomainDict
from .action_constants import API_ROOT_URL


class ActionCheckPaymentStatus(Action):
    def name(self) -> Text:
        return "action_check_payment_status"

    def translate_payment_status(self, status: str, method: str) -> Text:
        """Menerjemahkan status pembayaran mentah menjadi teks yang lebih mudah dibaca."""
        status_lower = status.lower() if status else "tidak diketahui"
        method_lower = method.lower() if method else ""

        if status_lower == "paid":
            return "Lunas (Sudah Dibayar)"
        elif status_lower == "pay_on_pickup":
            if "pay_at_store" in method_lower:
                return "Bayar di Toko (saat pengambilan)"
            return "Bayar di Tempat (saat pengambilan)"
        elif status_lower == "awaiting_gateway_interaction":
            return "Menunggu Pembayaran Online"
        elif status_lower == "pending_confirmation" and "pay_at_store" in method_lower:
            return "Menunggu Konfirmasi Pembayaran di Toko"
        elif status_lower == "cancelled_by_user":
            return "Dibatalkan oleh Pengguna"
        elif status_lower == "failed":
            return "Gagal"
        elif status_lower == "expired":
            return "Kedaluwarsa"
        return f"Status: {status.capitalize() if status else 'Tidak Diketahui'}"

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict
    ) -> List[Dict[Text, Any]]:

        request_url = f"{API_ROOT_URL}/order/all"
        metadata = tracker.latest_message.get("metadata")
        auth_token = None
        if metadata:
            auth_token = metadata.get("authToken")

        if not auth_token:
            dispatcher.utter_message(template="utter_auth_error")
            print(f"{self.name()}: authToken tidak ditemukan di metadata.")
            return []

        headers = {"Authorization": f"Bearer {auth_token}"}
        print(f"{self.name()}: Memanggil API {request_url} dengan token.")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(request_url, headers=headers) as response:
                    if response.status == 200:
                        response_data = await response.json()
                        if response_data.get("success"):
                            orders = response_data.get("data", [])
                            if orders:
                                dispatcher.utter_message(
                                    template="utter_payment_status_intro")
                                displayed_orders = 0
                                for order in orders[:5]:
                                    payment_details = order.get(
                                        "paymentDetails")
                                    order_id = order.get(
                                        "orderId", "ID Tidak Diketahui")
                                    shop_name = order.get("shopRingkas", {}).get(
                                        "shopName", "Toko tidak diketahui")
                                    items_desc_list = [item.get('name', 'item') for item in order.get(
                                        'items', [])[:2]]
                                    items_desc = ", ".join(items_desc_list)
                                    if len(order.get('items', [])) > 2:
                                        items_desc += " dll."

                                    message_parts = [
                                        f"- Pesanan **{order_id}** di **{shop_name}** ({items_desc}):"
                                    ]

                                    if payment_details:
                                        method = payment_details.get(
                                            "method", "Metode tidak diketahui")
                                        status = payment_details.get(
                                            "status", "Status tidak diketahui")

                                        readable_status = self.translate_payment_status(
                                            status, method)
                                        message_parts.append(
                                            f"  Status Pembayaran: **{readable_status}**")
                                        message_parts.append(
                                            f"  Metode: {method.replace('_', ' ').title()}")

                                        if status.lower() == "paid":
                                            confirmed_at = payment_details.get(
                                                "confirmedAt")
                                            if confirmed_at:
                                                message_parts.append(
                                                    f"  Dikonfirmasi pada: {confirmed_at.split('T')[0]}")
                                            confirmation_notes = payment_details.get(
                                                "confirmationNotes")
                                            if confirmation_notes:
                                                message_parts.append(
                                                    f"  Catatan Konfirmasi: {confirmation_notes}")

                                    else:
                                        message_parts.append(
                                            "  Detail pembayaran tidak tersedia.")

                                    dispatcher.utter_message(
                                        text="\n".join(message_parts))
                                    displayed_orders += 1

                                if displayed_orders == 0 and orders:
                                    dispatcher.utter_message(
                                        text="Tidak ada detail pembayaran yang bisa ditampilkan untuk pesanan Anda saat ini.")
                                elif not orders:
                                    dispatcher.utter_message(
                                        template="utter_no_orders_found")

                            else:
                                dispatcher.utter_message(
                                    template="utter_no_orders_found")

                        else:
                            error_message_from_api = response_data.get(
                                "message", "Gagal mengambil data pesanan.")
                            print(
                                f"{self.name()}: API success=false, message: {error_message_from_api}")
                            if "Akses ditolak" in error_message_from_api or "Token tidak disertakan" in error_message_from_api:
                                dispatcher.utter_message(
                                    template="utter_auth_error")
                            else:
                                dispatcher.utter_message(
                                    text=f"Info dari server: {error_message_from_api}")

                    elif response.status == 401 or response.status == 403:
                        print(
                            f"{self.name()}: API returned {response.status} (Unauthorized/Forbidden).")
                        dispatcher.utter_message(template="utter_auth_error")
                        error_text = await response.text()
                        print(
                            f"{self.name()}: API request failed with status: {response.status}, response: {error_text}")
                        dispatcher.utter_message(template="utter_api_error")

        except aiohttp.ClientConnectorError as e:
            print(f"{self.name()}: Connection Error: {e}")
            dispatcher.utter_message(
                text="Maaf, tidak dapat terhubung ke layanan pesanan.")
        except aiohttp.ContentTypeError as e:
            print(f"{self.name()}: Content Type Error (bukan JSON?): {e}")
            dispatcher.utter_message(
                text="Maaf, ada masalah dengan format data dari layanan pesanan.")
        except Exception as e:
            print(f"{self.name()}: An unexpected error occurred: {e}")
            dispatcher.utter_message(
                text="Maaf, terjadi kesalahan yang tidak terduga saat memproses permintaan Anda.")

        return []
