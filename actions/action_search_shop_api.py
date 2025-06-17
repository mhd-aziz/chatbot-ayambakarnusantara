import aiohttp
import urllib.parse
from typing import Any, Text, Dict, List

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
from rasa_sdk.types import DomainDict

from .action_constants import API_ROOT_URL


class ActionSearchShopAPI(Action):
    def name(self) -> Text:
        return "action_search_shop_api"

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict
    ) -> List[Dict[Text, Any]]:

        shop_search_term = next(
            tracker.get_latest_entity_values("shop_name"), None)
        if not shop_search_term:
            shop_search_term = tracker.get_slot("shop_name_slot")

        if not shop_search_term:
            print(
                "ERROR: shop_search_term is None in action_search_shop_api after collect step.")
            dispatcher.utter_message(
                text="Maaf, terjadi kesalahan dalam memproses nama toko.")
            return [SlotSet("shop_name_slot", None)]

        search_context_description = f"dengan nama '{shop_search_term}'"

        encoded_search_term = urllib.parse.quote_plus(shop_search_term)
        request_url = f"{API_ROOT_URL}/shop?searchByShopName={encoded_search_term}"

        print(f"Requesting shop data from URL: {request_url}")

        found_shops_details = []

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(request_url) as response:
                    if response.status == 200:
                        response_data = await response.json()
                        if response_data.get("success") and "data" in response_data and "shops" in response_data["data"]:
                            api_shops = response_data["data"]["shops"]
                            if not api_shops:
                                dispatcher.utter_message(
                                    text=f"Maaf, saya tidak menemukan toko {search_context_description}.")
                                return [SlotSet("shop_name_slot", None)]

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
                                "message", f"Gagal mencari toko '{shop_search_term}'.")
                            print(
                                f"API shop search reported an error for '{shop_search_term}': {api_message}")
                            dispatcher.utter_message(
                                text=f"Info dari server: {api_message}")
                            return [SlotSet("shop_name_slot", None)]
                        else:
                            print(
                                f"API shop search response format issue for '{shop_search_term}': {response_data}")
                            dispatcher.utter_message(
                                text="Format respons API pencarian toko tidak sesuai.")
                            return [SlotSet("shop_name_slot", None)]
                    else:
                        print(
                            f"API shop search request failed for '{shop_search_term}' with status: {response.status}")
                        error_text = await response.text()
                        print(f"API shop search error response: {error_text}")
                        dispatcher.utter_message(
                            text=f"Maaf, gagal mengambil data pencarian toko dari server (status: {response.status}).")
                        return [SlotSet("shop_name_slot", None)]

        except aiohttp.ClientConnectorError as e:
            print(
                f"Connection Error calling shop search API for '{shop_search_term}': {e}")
            dispatcher.utter_message(
                text="Maaf, tidak dapat terhubung ke layanan toko. Periksa koneksi Anda.")
            return [SlotSet("shop_name_slot", None)]
        except aiohttp.ContentTypeError as e:
            print(
                f"Content Type Error from shop search API for '{shop_search_term}' (not JSON?): {e}")
            dispatcher.utter_message(
                text="Maaf, ada masalah dengan format data dari layanan toko.")
            return [SlotSet("shop_name_slot", None)]
        except Exception as e:
            print(
                f"An unexpected error occurred while fetching shop search data for '{shop_search_term}': {e}")
            dispatcher.utter_message(
                text="Maaf, terjadi kesalahan yang tidak terduga saat memproses permintaan pencarian toko Anda.")
            return [SlotSet("shop_name_slot", None)]

        if found_shops_details:
            shops_to_display = found_shops_details[:5]
            message_parts = [
                f"Berikut hasil pencarian toko {search_context_description}:\n"]
            for shop_detail in shops_to_display:
                part = f"\n- **{shop_detail['name']}**\n"
                if shop_detail['address'] and shop_detail['address'].lower() != "alamat tidak tersedia":
                    part += f"  Alamat: {shop_detail['address']}\n"
                if shop_detail['owner_name'] and shop_detail['owner_name'].lower() != "nama pemilik tidak diketahui":
                    part += f"  Pemilik: {shop_detail['owner_name']}\n"
                if shop_detail['description'] and shop_detail['description'].lower() != "tidak ada deskripsi":
                    part += f"  Deskripsi: {shop_detail['description']}\n"
                if shop_detail['banner_image_url']:
                    part += f"  Banner: {shop_detail['banner_image_url']}\n"
                message_parts.append(part)

            if len(found_shops_details) > 5:
                message_parts.append(
                    f"\nDan {len(found_shops_details) - 5} toko lainnya yang cocok.")
            dispatcher.utter_message(text="".join(message_parts))

        return [SlotSet("shop_name_slot", None)]
