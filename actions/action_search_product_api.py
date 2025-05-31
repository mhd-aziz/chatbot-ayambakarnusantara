# actions/action_search_product_api.py
import aiohttp
import urllib.parse
from typing import Any, Text, Dict, List

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
from rasa_sdk.types import DomainDict

from .action_constants import API_ROOT_URL  # Impor konstanta


class ActionSearchProductAPI(Action):  # Nama kelas diubah
    def name(self) -> Text:
        return "action_search_product_api"  # Nama action untuk Rasa diubah

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict
    ) -> List[Dict[Text, Any]]:

        product_search_term = next(
            tracker.get_latest_entity_values("product_name"), None)
        if not product_search_term:
            product_search_term = tracker.get_slot("product_name_slot")

        if not product_search_term:
            # Pesan ini mungkin juga ingin Anda sesuaikan ke Bahasa Inggris nanti
            dispatcher.utter_message(text="Produk apa yang ingin Anda cari?")
            return [SlotSet("product_name_slot", None)]

        encoded_search_term = urllib.parse.quote_plus(product_search_term)
        request_url = f"{API_ROOT_URL}/product?searchByName={encoded_search_term}"

        print(f"Requesting product data from URL: {request_url}")

        found_products_details = []

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(request_url) as response:
                    if response.status == 200:
                        response_data = await response.json()
                        if response_data.get("success") and "data" in response_data and "products" in response_data["data"]:
                            api_products = response_data["data"]["products"]
                            if not api_products:
                                dispatcher.utter_message(
                                    text=f"Maaf, saya tidak menemukan produk dengan nama yang mirip '{product_search_term}'.")  # Pertimbangkan terjemahan
                                return [SlotSet("product_name_slot", None)]

                            for product in api_products:
                                found_products_details.append({
                                    "id": product.get("_id"),
                                    "name": product.get("name", "Nama tidak tersedia"),
                                    "price": product.get("price", "Harga tidak tersedia"),
                                    "description": product.get("description", ""),
                                    "stock": product.get("stock", "Tidak diketahui"),
                                    "category": product.get("category", "Tidak diketahui"),
                                    "image_url": product.get("productImageURL"),
                                    "average_rating": product.get("averageRating", 0.0),
                                    "rating_count": product.get("ratingCount", 0)
                                })

                            if found_products_details:
                                found_products_details.sort(
                                    key=lambda x: (
                                        x.get('average_rating', 0.0), x.get('rating_count', 0)),
                                    reverse=True
                                )
                        elif not response_data.get("success"):
                            api_message = response_data.get(
                                "message", "Gagal memproses permintaan produk di server.")
                            print(
                                f"API product reported an error for search term '{product_search_term}': {api_message}")
                            dispatcher.utter_message(
                                text=f"Info dari server: {api_message}")  # Pertimbangkan terjemahan
                            return [SlotSet("product_name_slot", None)]
                        else:
                            print(
                                f"API product response format issue for search term '{product_search_term}': {response_data}")
                            dispatcher.utter_message(
                                text="Format respons API produk tidak sesuai.")  # Pertimbangkan terjemahan
                            return [SlotSet("product_name_slot", None)]
                    else:
                        print(
                            f"API product request failed for search term '{product_search_term}' with status: {response.status}")
                        error_text = await response.text()
                        print(f"API product error response: {error_text}")
                        dispatcher.utter_message(
                            # Pertimbangkan terjemahan
                            text=f"Maaf, gagal mengambil data produk dari server (status: {response.status})."
                        )
                        return [SlotSet("product_name_slot", None)]
        except aiohttp.ClientConnectorError as e:
            print(
                f"Connection Error calling product API for search term '{product_search_term}': {e}")
            dispatcher.utter_message(
                text="Maaf, tidak dapat terhubung ke layanan produk. Periksa koneksi Anda.")  # Pertimbangkan terjemahan
            return [SlotSet("product_name_slot", None)]
        except aiohttp.ContentTypeError as e:
            print(
                f"Content Type Error from product API for search term '{product_search_term}' (not JSON?): {e}")
            dispatcher.utter_message(
                text="Maaf, ada masalah dengan format data dari layanan produk.")  # Pertimbangkan terjemahan
            return [SlotSet("product_name_slot", None)]
        except Exception as e:
            print(
                f"An unexpected error occurred for product search term '{product_search_term}': {e}")
            dispatcher.utter_message(
                text="Maaf, terjadi kesalahan yang tidak terduga saat memproses permintaan produk Anda.")  # Pertimbangkan terjemahan
            return [SlotSet("product_name_slot", None)]

        if found_products_details:
            products_to_display = found_products_details[:5]
            message_parts = [
                f"Berikut produk yang kami temukan untuk '{product_search_term}':\n"]  # Pertimbangkan terjemahan

            for product_detail in products_to_display:
                part = f"\n- **{product_detail['name']}**"
                avg_rating = product_detail.get('average_rating', 0.0)
                rating_count = product_detail.get('rating_count', 0)
                if rating_count > 0:
                    part += f" (⭐ {avg_rating:.1f}/5 dari {rating_count} ulasan)"
                part += "\n"
                part += f"  Harga: Rp {product_detail['price']}\n"
                part += f"  Kategori: {product_detail['category']}\n"
                part += f"  Stok: {product_detail['stock']}\n"
                if product_detail['image_url']:
                    part += f"  Foto: {product_detail['image_url']}\n"
                if avg_rating >= 4.5 and rating_count >= 3:
                    part += "  ✨ *Menu ini sangat direkomendasikan!*\n"
                elif avg_rating >= 4.0 and rating_count >= 1:
                    part += "  👍 *Rating menu ini bagus!*\n"
                message_parts.append(part)

            if len(found_products_details) > 5:
                message_parts.append(
                    f"\nDan {len(found_products_details) - 5} produk lainnya.")  # Pertimbangkan terjemahan
            dispatcher.utter_message(text="".join(message_parts))
        return [SlotSet("product_name_slot", None)]
