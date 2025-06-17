import aiohttp
from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
from rasa_sdk.types import DomainDict

from .action_constants import API_ROOT_URL


class ActionRecommendProducts(Action):
    def name(self) -> Text:
        return "action_recommend_products"

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict
    ) -> List[Dict[Text, Any]]:

        print("Action 'action_recommend_products' dipanggil.")

        user_query_context = "produk"
        request_url = f"{API_ROOT_URL}/product/recommendations"

        print(f"Requesting product recommendations from URL: {request_url}")

        recommended_products_details = []
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(request_url) as response:
                    if response.status == 200:
                        response_data = await response.json()
                        if response_data.get("success") and "data" in response_data and "recommendations" in response_data["data"]:
                            api_recommendations = response_data["data"]["recommendations"]
                            for product in api_recommendations:
                                recommended_products_details.append({
                                    "id": product.get("_id"),
                                    "name": product.get("name", "Nama tidak tersedia"),
                                    "price": product.get("price", 0),
                                    "category": product.get("category", "Tidak diketahui"),
                                    "image_url": product.get("productImageURL"),
                                    "average_rating": product.get("averageRating", 0.0),
                                    "rating_count": product.get("ratingCount", 0)
                                })
                        elif not response_data.get("success"):
                            api_message = response_data.get(
                                "message", "Gagal mengambil data rekomendasi produk.")
                            dispatcher.utter_message(
                                text=f"Info dari server saat mengambil rekomendasi: {api_message}")
                            return []
                        else:
                            dispatcher.utter_message(
                                text="Format API rekomendasi produk tidak sesuai.")
                            return []
                    else:
                        error_text = await response.text()
                        print(
                            f"API recommendation request failed with status: {response.status}, response: {error_text}")
                        dispatcher.utter_message(
                            text=f"Gagal mengambil data rekomendasi produk dari server (status: {response.status}).")
                        return []
        except aiohttp.ClientConnectorError as e:
            print(f"Connection Error calling recommendation API: {e}")
            dispatcher.utter_message(
                text="Maaf, tidak dapat terhubung ke layanan produk untuk rekomendasi. Periksa koneksi Anda.")
            return []
        except aiohttp.ContentTypeError as e:
            print(
                f"Content Type Error from recommendation API (not JSON?): {e}")
            dispatcher.utter_message(
                text="Maaf, ada masalah dengan format data dari layanan rekomendasi produk.")
            return []
        except Exception as e:
            print(
                f"An unexpected error occurred in ActionRecommendProducts: {e}")
            dispatcher.utter_message(
                text="Maaf, terjadi kesalahan yang tidak terduga saat mencoba memberikan rekomendasi produk.")
            return []

        if not recommended_products_details:
            dispatcher.utter_message(
                text=f"Maaf, saya tidak menemukan {user_query_context} yang bisa direkomendasikan saat ini.")
            return []

        recommended_products_details.sort(
            key=lambda x: (x.get('average_rating', 0.0),
                           x.get('rating_count', 0)),
            reverse=True
        )

        products_to_display = recommended_products_details

        if products_to_display:
            message_parts = [
                f"Berikut semua {user_query_context} rekomendasi terbaik dari kami:\n"]
            for product in products_to_display:
                part = f"\n- **{product['name']}**"
                avg_rating = product.get('average_rating', 0.0)
                rating_count = product.get('rating_count', 0)
                if rating_count > 0:
                    part += f" (⭐ {avg_rating:.1f}/5 dari {rating_count} ulasan)"
                part += "\n"
                part += f"  Harga: Rp {product['price']}\n"
                part += f"  Kategori: {product['category']}\n"
                if product.get('image_url'):
                    part += f"  Foto: {product['image_url']}\n"

                if avg_rating >= 4.5 and rating_count >= 3:
                    part += "  ✨ *Produk ini sangat direkomendasikan!*\n"
                elif avg_rating >= 4.0 and rating_count >= 1:
                    part += "  👍 *Rating produk ini bagus!*\n"
                message_parts.append(part)

            dispatcher.utter_message(text="".join(message_parts))
        else:
            dispatcher.utter_message(
                text=f"Maaf, saya tidak menemukan {user_query_context} yang menonjol untuk direkomendasikan saat ini.")

        return []
