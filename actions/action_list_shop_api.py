import aiohttp
from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
from rasa_sdk.types import DomainDict
from .action_constants import API_ROOT_URL


class ActionListShopsAPI(Action):
    def name(self) -> Text:
        return "action_list_shops_api"

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict
    ) -> List[Dict[Text, Any]]:

        request_url = f"{API_ROOT_URL}/shop"
        print(f"Requesting all shops data from URL: {request_url}")

        found_shops_details = []

        dispatcher.utter_message(
            text="Baik, saya carikan daftar semua toko yang tersedia...")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(request_url) as response:
                    if response.status == 200:
                        response_data = await response.json()
                        if response_data.get("success") and "data" in response_data and "shops" in response_data["data"]:
                            api_shops = response_data["data"]["shops"]
                            if not api_shops:
                                dispatcher.utter_message(
                                    text="Maaf, saat ini tidak ada toko yang terdaftar.")
                                return []

                            for shop in api_shops:
                                found_shops_details.append({
                                    "name": shop.get("shopName", "Nama toko tidak tersedia"),
                                    "address": shop.get("shopAddress", "Alamat tidak tersedia"),
                                    "description": shop.get("description", "Tidak ada deskripsi"),
                                    "banner_image_url": shop.get("bannerImageURL"),
                                    "owner_name": shop.get("ownerName", "Nama pemilik tidak diketahui")
                                })

                            if found_shops_details:
                                found_shops_details.sort(
                                    key=lambda x: x.get('name', '').lower())

                        elif not response_data.get("success"):
                            api_message = response_data.get(
                                "message", "Gagal mengambil daftar semua toko dari server.")
                            print(
                                f"API list all shops reported an error: {api_message}")
                            dispatcher.utter_message(
                                text=f"Info dari server: {api_message}")
                            return []
                        else:
                            print(
                                f"API list all shops response format issue: {response_data}")
                            dispatcher.utter_message(
                                text="Format respons API daftar semua toko tidak sesuai.")
                            return []
                    else:
                        print(
                            f"API list all shops request failed with status: {response.status}")
                        error_text = await response.text()
                        print(
                            f"API list all shops error response: {error_text}")
                        dispatcher.utter_message(
                            text=f"Maaf, gagal mengambil daftar semua toko dari server (status: {response.status}).")
                        return []

        except aiohttp.ClientConnectorError as e:
            print(f"Connection Error calling list all shops API: {e}")
            dispatcher.utter_message(
                text="Maaf, tidak dapat terhubung ke layanan toko. Periksa koneksi Anda.")
            return []
        except aiohttp.ContentTypeError as e:
            print(
                f"Content Type Error from list all shops API (not JSON?): {e}")
            dispatcher.utter_message(
                text="Maaf, ada masalah dengan format data dari layanan toko.")
            return []
        except Exception as e:
            print(
                f"An unexpected error occurred while fetching all shops data: {e}")
            dispatcher.utter_message(
                text="Maaf, terjadi kesalahan yang tidak terduga saat memproses permintaan daftar toko Anda.")
            return []

        if found_shops_details:
            shops_to_display = found_shops_details[:10]
            message_parts = [
                "Berikut adalah daftar toko yang tersedia:\n"]
            for shop_detail in shops_to_display:
                part = f"\n- **{shop_detail['name']}**\n"
                if shop_detail['address'] and shop_detail['address'].lower() != "alamat tidak tersedia":
                    part += f"  Alamat: {shop_detail['address']}\n"
                if shop_detail['owner_name'] and shop_detail['owner_name'].lower() != "nama pemilik tidak diketahui":
                    part += f"  Pemilik: {shop_detail['owner_name']}\n"
                if shop_detail['banner_image_url']:
                    part += f"  Banner: {shop_detail['banner_image_url']}\n"
                message_parts.append(part)

            if len(found_shops_details) > 10:
                message_parts.append(
                    f"\n...dan {len(found_shops_details) - 10} toko lainnya.")

            dispatcher.utter_message(text="".join(message_parts))

        return []
