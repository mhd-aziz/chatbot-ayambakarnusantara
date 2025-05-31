# actions/action_search_shop_api.py
import aiohttp
import urllib.parse
from typing import Any, Text, Dict, List

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
from rasa_sdk.types import DomainDict

from .action_constants import API_ROOT_URL


class ActionSearchShopAPI(Action):  # Nama kelas diubah
    def name(self) -> Text:
        return "action_search_shop_api"  # Nama action untuk Rasa diubah

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict
    ) -> List[Dict[Text, Any]]:

        shop_name_entity = next(
            tracker.get_latest_entity_values("shop_name"), None)

        params = {}
        search_context_description = "semua toko yang tersedia" 

        if shop_name_entity:
            params["searchByShopName"] = shop_name_entity
            search_context_description = f"dengan nama '{shop_name_entity}'"

        request_url = f"{API_ROOT_URL}/shop"
        if params:
            query_string = urllib.parse.urlencode(params)
            request_url = f"{request_url}?{query_string}"

        print(f"Requesting shop data from URL: {request_url}")

        found_shops_details = []

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(request_url) as response:
                    if response.status == 200:
                        response_data = await response.json()
                        if response_data.get("success"):
                            if "data" in response_data and "shops" in response_data["data"]:
                                api_shops = response_data["data"]["shops"]
                                if api_shops:
                                    for shop in api_shops:
                                        found_shops_details.append({
                                            "name": shop.get("shopName", "Nama toko tidak tersedia"),
                                            "address": shop.get("shopAddress", "Alamat tidak tersedia"),
                                            "description": shop.get("description", "Tidak ada deskripsi"),
                                            "banner_image_url": shop.get("bannerImageURL"),
                                            "owner_name": shop.get("ownerName", "Nama pemilik tidak diketahui")
                                        })
                                else:
                                    dispatcher.utter_message(
                                        text=f"Tidak ada toko yang ditemukan {search_context_description}.")  
                                    return []
                            else:
                                print(
                                    f"API shop response format issue (missing 'data' or 'shops' key): {response_data}")
                                dispatcher.utter_message(
                                    text="Format respons API toko tidak sesuai.")  
                                return []
                        else:
                            api_message = response_data.get(
                                "message", "Gagal mengambil daftar toko dari server.")
                            print(f"API shop reported an error: {api_message}")
                            dispatcher.utter_message(
                                text=f"Info dari server: {api_message}")  
                            return []
                    else:
                        print(
                            f"API shop request failed with status: {response.status}")
                        error_text = await response.text()
                        print(f"API shop error response: {error_text}")
                        dispatcher.utter_message(
                            text=f"Maaf, gagal mengambil data toko dari server (status: {response.status}).")  
                        return []
        except aiohttp.ClientConnectorError as e:
            print(f"Connection Error calling shop API: {e}")
            dispatcher.utter_message(
                text="Maaf, tidak dapat terhubung ke layanan toko. Periksa koneksi Anda.") 
            return []
        except aiohttp.ContentTypeError as e:
            print(f"Content Type Error from shop API (not JSON?): {e}")
            dispatcher.utter_message(
                text="Maaf, ada masalah dengan format data dari layanan toko.")  
            return []
        except Exception as e:
            print(
                f"An unexpected error occurred while fetching shop data: {e}")
            dispatcher.utter_message(
                text="Maaf, terjadi kesalahan yang tidak terduga saat memproses permintaan toko Anda.")  
            return []

        if found_shops_details:
            shops_to_display = found_shops_details[:5]
            message_parts = [
                f"Berikut toko yang kami temukan {search_context_description}:\n"] 
            for shop_detail in shops_to_display:
                part = f"\n- **{shop_detail['name']}**\n"
                if shop_detail['address'] and shop_detail['address'] != "Alamat tidak tersedia":
                    part += f"  Alamat: {shop_detail['address']}\n"
                part += f"  Pemilik: {shop_detail['owner_name']}\n"
                if shop_detail['description'] and shop_detail['description'] != "Tidak ada deskripsi":
                    part += f"  Deskripsi: {shop_detail['description']}\n"
                if shop_detail['banner_image_url']:
                    part += f"  Banner: {shop_detail['banner_image_url']}\n"
                message_parts.append(part)
            if len(found_shops_details) > 5:
                message_parts.append(
                    f"\nDan {len(found_shops_details) - 5} toko lainnya.") 
            dispatcher.utter_message(text="".join(message_parts))
        return []
