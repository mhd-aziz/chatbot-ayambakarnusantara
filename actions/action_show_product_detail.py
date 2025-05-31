# actions/action_show_product_detail.py
import aiohttp
import urllib.parse
from typing import Any, Text, Dict, List

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
from rasa_sdk.types import DomainDict

from .action_constants import API_ROOT_URL


class ActionShowProductDetail(Action):
    def name(self) -> Text:
        return "action_show_product_detail"

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict
    ) -> List[Dict[Text, Any]]:

        product_name_to_detail = tracker.get_slot("product_name_slot")
        latest_product_entity = next(
            tracker.get_latest_entity_values("product_name"), None)
        if latest_product_entity:
            product_name_to_detail = latest_product_entity

        print(
            f"Action 'action_show_product_detail' dipanggil untuk produk: {product_name_to_detail}")

        if not product_name_to_detail:
            dispatcher.utter_message(
                text="Produk mana yang ingin Anda lihat detailnya? Mohon sebutkan namanya.")
            return []

        product_id_found = None
        try:
            encoded_search_term = urllib.parse.quote_plus(
                product_name_to_detail)
            # URL untuk mencari produk berdasarkan nama untuk mendapatkan ID-nya
            search_url = f"{API_ROOT_URL}/product?searchByName={encoded_search_term}"
            print(f"Mencari ID produk dengan URL: {search_url}")

            async with aiohttp.ClientSession() as session:
                async with session.get(search_url) as search_response:
                    if search_response.status == 200:
                        search_data = await search_response.json()
                        if search_data.get("success") and "data" in search_data and "products" in search_data["data"]:
                            api_products = search_data["data"]["products"]
                            if api_products:
                                # Cari produk yang namanya paling cocok (case-insensitive)
                                for prod in api_products:
                                    if prod.get("name", "").lower() == product_name_to_detail.lower():
                                        product_id_found = prod.get("_id")
                                        break
                                # Jika tidak ada yang cocok persis, ambil ID produk pertama dari hasil pencarian
                                if not product_id_found:
                                    product_id_found = api_products[0].get(
                                        "_id")

                                if not product_id_found:  # Seharusnya tidak terjadi jika api_products tidak kosong
                                    print(
                                        f"Tidak ditemukan ID untuk produk '{product_name_to_detail}' dari hasil pencarian.")
                            else:
                                print(
                                    f"Array produk kosong saat mencari ID untuk '{product_name_to_detail}'.")
                        else:
                            print(
                                f"Format API pencarian tidak sesuai atau success=false saat mencari ID. Data: {search_data}")
                    else:
                        print(
                            f"Pencarian ID produk gagal dengan status: {search_response.status}")

            if not product_id_found:
                dispatcher.utter_message(
                    text=f"Maaf, saya tidak bisa menemukan detail untuk produk '{product_name_to_detail}'. Mungkin nama produknya kurang spesifik atau tidak ada?")
                return [SlotSet("product_name_slot", None)]

            # Gunakan ID yang ditemukan untuk mengambil detail produk
            detail_url = f"{API_ROOT_URL}/product/{product_id_found}"
            print(f"Mengambil detail produk dari URL: {detail_url}")

            async with aiohttp.ClientSession() as session:  # Sesi baru untuk request detail
                async with session.get(detail_url) as detail_response:
                    if detail_response.status == 200:
                        detail_data = await detail_response.json()
                        if detail_data.get("success") and "data" in detail_data:
                            product_detail = detail_data["data"]
                            name = product_detail.get(
                                "name", "Nama tidak tersedia")
                            description = product_detail.get(
                                "description", "Tidak ada deskripsi.")
                            price = product_detail.get(
                                "price", "Harga tidak tersedia")
                            category = product_detail.get(
                                "category", "Kategori tidak diketahui")
                            stock = product_detail.get(
                                "stock", "Stok tidak diketahui")
                            image_url = product_detail.get("productImageURL")
                            avg_rating = product_detail.get(
                                "averageRating", 0.0)
                            rating_count = product_detail.get("ratingCount", 0)

                            message = f"Berikut detail untuk **{name}**:\n"
                            if description and description.lower() != "tidak ada deskripsi.":
                                message += f"- Deskripsi: {description}\n"
                            message += f"- Harga: Rp {price}\n"
                            message += f"- Kategori: {category}\n"
                            message += f"- Stok: {stock}\n"
                            if rating_count > 0:
                                message += f"- Rating: ⭐ {avg_rating:.1f}/5 ({rating_count} ulasan)\n"
                            else:
                                message += f"- Rating: Belum ada ulasan\n"
                            if image_url:
                                message += f"- Foto: {image_url}\n"
                            dispatcher.utter_message(text=message)
                        elif not detail_data.get("success"):
                            api_message = detail_data.get(
                                "message", "Gagal mengambil detail produk.")
                            dispatcher.utter_message(
                                text=f"Info dari server: {api_message}")
                        else:
                            dispatcher.utter_message(
                                text="Format respons API detail produk tidak sesuai.")
                    else:
                        error_text = await detail_response.text()
                        print(
                            f"API detail product request failed with status: {detail_response.status}, response: {error_text}")
                        dispatcher.utter_message(
                            text=f"Maaf, gagal mengambil detail produk dari server (status: {detail_response.status}).")
        except aiohttp.ClientConnectorError as e:
            print(f"Connection Error in ActionShowProductDetail: {e}")
            dispatcher.utter_message(
                text="Maaf, tidak dapat terhubung ke layanan produk.")
        except aiohttp.ContentTypeError as e:
            print(
                f"Content Type Error in ActionShowProductDetail (not JSON?): {e}")
            dispatcher.utter_message(
                text="Maaf, ada masalah dengan format data dari layanan produk.")
        except Exception as e:
            print(
                f"An unexpected error occurred in ActionShowProductDetail: {e}")
            dispatcher.utter_message(
                text="Maaf, terjadi kesalahan yang tidak terduga saat memproses permintaan Anda.")
        return [SlotSet("product_name_slot", None)]
