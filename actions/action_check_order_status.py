import aiohttp
from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
from rasa_sdk.types import DomainDict
from .action_constants import API_ROOT_URL


class ActionCheckOrderStatus(Action):
    def name(self) -> Text:
        return "action_check_order_status"

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
            print("ActionCheckOrderStatus: authToken tidak ditemukan di metadata.")
            return []

        headers = {"Authorization": f"Bearer {auth_token}"}
        print(
            f"ActionCheckOrderStatus: Memanggil API {request_url} dengan token.")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(request_url, headers=headers) as response:
                    if response.status == 200:
                        response_data = await response.json()
                        if response_data.get("success"):
                            orders = response_data.get("data", [])
                            if orders:
                                dispatcher.utter_message(
                                    template="utter_orders_found_intro")
                                for order in orders[:3]:
                                    items_desc = ", ".join(
                                        [item.get('name', 'item') for item in order.get('items', [])])
                                    shop_name = order.get("shopRingkas", {}).get(
                                        "shopName", "Toko tidak diketahui")

                                    order_status_translate = {
                                        "PENDING_CONFIRMATION": "Menunggu Konfirmasi Penjual",
                                        "AWAITING_PAYMENT": "Menunggu Pembayaran",
                                        "PROCESSING": "Sedang Diproses",
                                        "READY_FOR_PICKUP": "Siap Diambil",
                                        "OUT_FOR_DELIVERY": "Sedang Diantar",
                                        "COMPLETED": "Selesai",
                                        "CANCELLED": "Dibatalkan",
                                        "FAILED": "Gagal"
                                    }
                                    display_status = order_status_translate.get(order.get(
                                        'orderStatus', 'Status Tidak Diketahui').upper(), order.get('orderStatus', 'Status Tidak Diketahui'))

                                    message = (
                                        f"- Pesanan **{order.get('orderId')}** di **{shop_name}**\n"
                                        f"  Status: **{display_status}**\n"
                                        f"  Total: Rp {order.get('totalPrice')}\n"
                                        f"  Item: {items_desc}\n"
                                        f"  Dipesan pada: {order.get('createdAt', '').split('T')[0]}"
                                    )
                                    dispatcher.utter_message(text=message)
                                if not orders:
                                    dispatcher.utter_message(
                                        template="utter_no_orders_found")
                            else:
                                error_message_from_api = response_data.get(
                                    "message", "Gagal mengambil data pesanan.")
                                print(
                                    f"ActionCheckOrderStatus: API success=false, message: {error_message_from_api}")
                                if "Akses ditolak" in error_message_from_api or "Token tidak disertakan" in error_message_from_api:
                                    dispatcher.utter_message(
                                        template="utter_auth_error")
                                else:
                                    dispatcher.utter_message(
                                        text=f"Info dari server: {error_message_from_api}")
                        else:
                            error_text = await response.text()
                            print(
                                f"ActionCheckOrderStatus: API request failed with status: {response.status}, response: {error_text}")
                            dispatcher.utter_message(
                                template="utter_api_error")
                    elif response.status == 401 or response.status == 403:
                        print(
                            f"ActionCheckOrderStatus: API returned {response.status} (Unauthorized/Forbidden).")
                        dispatcher.utter_message(template="utter_auth_error")
                    else:
                        print(
                            f"ActionCheckOrderStatus: API request failed with status: {response.status}.")
                        dispatcher.utter_message(template="utter_api_error")

        except aiohttp.ClientConnectorError as e:
            print(f"ActionCheckOrderStatus: Connection Error: {e}")
            dispatcher.utter_message(
                text="Maaf, tidak dapat terhubung ke layanan pesanan.")
        except aiohttp.ContentTypeError as e:
            print(
                f"ActionCheckOrderStatus: Content Type Error (bukan JSON?): {e}")
            dispatcher.utter_message(
                text="Maaf, ada masalah dengan format data dari layanan pesanan.")
        except Exception as e:
            print(f"ActionCheckOrderStatus: An unexpected error occurred: {e}")
            dispatcher.utter_message(
                text="Maaf, terjadi kesalahan yang tidak terduga saat memproses permintaan Anda.")

        return []
