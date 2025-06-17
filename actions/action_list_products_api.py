import aiohttp
from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
from rasa_sdk.types import DomainDict
from .action_constants import API_ROOT_URL


class ActionListProductsAPI(Action):
    def name(self) -> Text:
        return "action_list_products_api"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict
                  ) -> List[Dict[Text, Any]]:

        request_url = f"{API_ROOT_URL}/product"
        print(f"Requesting all products from URL: {request_url}")

        all_products_details = []

        dispatcher.utter_message(
            text="Baik, saya carikan daftar semua produk yang tersedia...")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(request_url) as response:
                    if response.status == 200:
                        response_data = await response.json()
                        if response_data.get("success") and "data" in response_data and "products" in response_data["data"]:
                            api_products = response_data["data"]["products"]
                            if not api_products:
                                dispatcher.utter_message(
                                    text="Maaf, saat ini tidak ada produk yang tersedia.")
                                return []

                            for product in api_products:
                                all_products_details.append({
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

                            if all_products_details:
                                all_products_details.sort(
                                    key=lambda x: (
                                        x.get('average_rating', 0.0), x.get('rating_count', 0)),
                                    reverse=True
                                )
                        elif not response_data.get("success"):
                            api_message = response_data.get(
                                "message", "Gagal memproses permintaan daftar produk di server.")
                            print(
                                f"API list all products reported an error: {api_message}")
                            dispatcher.utter_message(
                                text=f"Info dari server: {api_message}")
                            return []
                        else:
                            print(
                                f"API list all products response format issue: {response_data}")
                            dispatcher.utter_message(
                                text="Format respons API daftar produk tidak sesuai.")
                            return []
                    else:
                        print(
                            f"API list all products request failed with status: {response.status}")
                        error_text = await response.text()
                        print(
                            f"API list all products error response: {error_text}")
                        dispatcher.utter_message(
                            text=f"Maaf, gagal mengambil daftar produk dari server (status: {response.status})."
                        )
                        return []
        except aiohttp.ClientConnectorError as e:
            print(f"Connection Error calling list all products API: {e}")
            dispatcher.utter_message(
                text="Maaf, tidak dapat terhubung ke layanan produk. Periksa koneksi Anda.")
            return []
        except aiohttp.ContentTypeError as e:
            print(
                f"Content Type Error from list all products API (not JSON?): {e}")
            dispatcher.utter_message(
                text="Maaf, ada masalah dengan format data dari layanan produk.")
            return []
        except Exception as e:
            print(
                f"An unexpected error occurred while listing all products: {e}")
            dispatcher.utter_message(
                text="Maaf, terjadi kesalahan yang tidak terduga saat memproses permintaan daftar produk Anda.")
            return []

        if all_products_details:
            products_to_display = all_products_details[:10]

            message_parts = [
                "Berikut adalah daftar produk yang tersedia:\n"]

            for product_detail in products_to_display:
                part = f"\n- **{product_detail['name']}**"
                avg_rating = product_detail.get('average_rating', 0.0)
                rating_count = product_detail.get('rating_count', 0)
                if rating_count > 0:
                    part += f" (⭐ {avg_rating:.1f}/5 dari {rating_count} ulasan)"
                part += "\n"
                part += f"  Harga: Rp {product_detail['price']}\n"
                part += f"  Kategori: {product_detail['category']}\n"
                if product_detail['image_url']:
                    part += f"  Foto: {product_detail['image_url']}\n"
                if avg_rating >= 4.5 and rating_count >= 3:
                    part += "  ✨ *Menu ini sangat direkomendasikan!*\n"
                elif avg_rating >= 4.0 and rating_count >= 1:
                    part += "  👍 *Rating menu ini bagus!*\n"
                message_parts.append(part)

            if len(all_products_details) > 10:
                message_parts.append(
                    f"\n...dan {len(all_products_details) - 10} produk lainnya.")

            dispatcher.utter_message(text="".join(message_parts))

        elif not all_products_details:
            dispatcher.utter_message(
                text="Maaf, saat ini tidak ada produk yang dapat ditampilkan.")

        return []
