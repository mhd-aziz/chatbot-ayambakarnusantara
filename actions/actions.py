import os
import aiohttp
import urllib.parse
from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet

API_ROOT_URL = "https://backend-dev-ayambakarnusantara-1013559069503.asia-southeast1.run.app"


class ActionCariProdukAPI(Action):
    def name(self) -> Text:
        return "action_cari_produk_api"

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:

        product_search_term = next(
            tracker.get_latest_entity_values("product_name"), None)
        if not product_search_term:
            product_search_term = tracker.get_slot("product_name_slot")

        if not product_search_term:
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
                                    text=f"Maaf, saya tidak menemukan produk dengan nama yang mirip '{product_search_term}'.")
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
                                text=f"Info dari server: {api_message}")
                            return [SlotSet("product_name_slot", None)]
                        else:
                            print(
                                f"API product response format issue for search term '{product_search_term}': {response_data}")
                            dispatcher.utter_message(
                                text="Format respons API produk tidak sesuai.")
                            return [SlotSet("product_name_slot", None)]
                    else:
                        print(
                            f"API product request failed for search term '{product_search_term}' with status: {response.status}")
                        error_text = await response.text()
                        print(f"API product error response: {error_text}")
                        dispatcher.utter_message(
                            text=f"Maaf, gagal mengambil data produk dari server (status: {response.status})."
                        )
                        return [SlotSet("product_name_slot", None)]
        except aiohttp.ClientConnectorError as e:
            print(
                f"Connection Error calling product API for search term '{product_search_term}': {e}")
            dispatcher.utter_message(
                text="Maaf, tidak dapat terhubung ke layanan produk. Periksa koneksi Anda.")
            return [SlotSet("product_name_slot", None)]
        except aiohttp.ContentTypeError as e:
            print(
                f"Content Type Error from product API for search term '{product_search_term}' (not JSON?): {e}")
            dispatcher.utter_message(
                text="Maaf, ada masalah dengan format data dari layanan produk.")
            return [SlotSet("product_name_slot", None)]
        except Exception as e:
            print(
                f"An unexpected error occurred for product search term '{product_search_term}': {e}")
            dispatcher.utter_message(
                text="Maaf, terjadi kesalahan yang tidak terduga saat memproses permintaan produk Anda.")
            return [SlotSet("product_name_slot", None)]

        if found_products_details:
            products_to_display = found_products_details[:5]
            message_parts = [
                f"Berikut produk yang kami temukan untuk '{product_search_term}' (diurutkan berdasarkan rating terbaik):\n"]

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
                    f"\nDan {len(found_products_details) - 5} produk lainnya (yang juga sudah diurutkan berdasarkan rating).")
            dispatcher.utter_message(text="".join(message_parts))
        return [SlotSet("product_name_slot", None)]


class ActionCariTokoAPI(Action):
    def name(self) -> Text:
        return "action_cari_toko_api"

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]
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


class ActionRecommendProducts(Action):
    def name(self) -> Text:
        return "action_recommend_products"

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:

        print("Action 'action_recommend_products' dipanggil.")

        recommendation_query_term = next(
            tracker.get_latest_entity_values("product_name"), None)
        search_term_for_api = ""
        user_query_context = "umum"

        if recommendation_query_term:
            search_term_for_api = recommendation_query_term
            user_query_context = f"untuk '{recommendation_query_term}'"
            print(f"Rekomendasi diminta dengan query: {search_term_for_api}")
        else:
            print("Rekomendasi umum diminta.")

        encoded_search_term = urllib.parse.quote_plus(search_term_for_api)
        request_url = f"{API_ROOT_URL}/product?searchByName={encoded_search_term}"
        if not search_term_for_api:
            print("Karena tidak ada query spesifik, mengambil semua produk untuk rekomendasi (asumsi API mendukung searchByName kosong).")

        print(
            f"Requesting products for recommendations from URL: {request_url}")

        all_fetched_products = []
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(request_url) as response:
                    if response.status == 200:
                        response_data = await response.json()
                        if response_data.get("success") and "data" in response_data and "products" in response_data["data"]:
                            api_products = response_data["data"]["products"]
                            for product in api_products:
                                all_fetched_products.append({
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
                                "message", "Gagal mengambil data produk.")
                            dispatcher.utter_message(
                                text=f"Info dari server saat mengambil rekomendasi: {api_message}")
                            return []
                        else:
                            dispatcher.utter_message(
                                text="Format API produk tidak sesuai saat mengambil rekomendasi.")
                            return []
                    else:
                        dispatcher.utter_message(
                            text=f"Gagal mengambil data produk untuk rekomendasi (status: {response.status}).")
                        return []
        except Exception as e:
            print(f"Error di ActionRecommendProducts saat mengambil data: {e}")
            dispatcher.utter_message(
                text="Maaf, terjadi kesalahan saat mencoba memberikan rekomendasi.")
            return []

        if not all_fetched_products:
            dispatcher.utter_message(
                text=f"Maaf, saya tidak menemukan produk yang bisa direkomendasikan {user_query_context} saat ini.")
            return []

        # Turunkan threshold untuk lebih banyak hasil
        MIN_RATING_COUNT_FOR_RECOMMENDATION = 1
        eligible_products = [
            p for p in all_fetched_products
            if p.get('rating_count', 0) >= MIN_RATING_COUNT_FOR_RECOMMENDATION and p.get('average_rating', 0.0) > 0
        ]

        if not eligible_products:
            if all_fetched_products:
                print(
                    f"Tidak ada produk yang memenuhi syarat rating count >= {MIN_RATING_COUNT_FOR_RECOMMENDATION} dan rating > 0. Mengurutkan semua produk yang diambil.")
                eligible_products = all_fetched_products
            else:
                dispatcher.utter_message(
                    text=f"Maaf, tidak ada produk yang bisa direkomendasikan {user_query_context} saat ini.")
                return []

        eligible_products.sort(
            key=lambda x: (x.get('average_rating', 0.0),
                           x.get('rating_count', 0)),
            reverse=True
        )

        recommended_products_to_display = eligible_products[:3]

        if recommended_products_to_display:
            message_parts = [
                f"Berikut beberapa produk rekomendasi terbaik {user_query_context} dari kami (berdasarkan rating):\n"]
            for product in recommended_products_to_display:
                part = f"\n- **{product['name']}**"
                avg_rating = product.get('average_rating', 0.0)
                rating_count = product.get('rating_count', 0)
                if rating_count > 0:  # Seharusnya sudah difilter, tapi cek lagi untuk tampilan
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

            if len(eligible_products) > 3:
                message_parts.append(
                    f"\nDan {len(eligible_products) - 3} produk lain yang juga bagus.")

            dispatcher.utter_message(text="".join(message_parts))
        else:
            dispatcher.utter_message(
                text=f"Maaf, saya tidak menemukan rekomendasi produk yang menonjol {user_query_context} saat ini.")

        return []


class ActionShowProductDetail(Action):
    def name(self) -> Text:
        return "action_show_product_detail"

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]
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
            search_url = f"{API_ROOT_URL}/product?searchByName={encoded_search_term}"
            print(f"Mencari ID produk dengan URL: {search_url}")

            async with aiohttp.ClientSession() as session:
                async with session.get(search_url) as search_response:
                    if search_response.status == 200:
                        search_data = await search_response.json()
                        if search_data.get("success") and "data" in search_data and "products" in search_data["data"]:
                            api_products = search_data["data"]["products"]
                            if api_products:
                                for prod in api_products:
                                    if prod.get("name", "").lower() == product_name_to_detail.lower():
                                        product_id_found = prod.get("_id")
                                        break
                                if not product_id_found:
                                    product_id_found = api_products[0].get(
                                        "_id")
                                if not product_id_found:
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
                    text=f"Maaf, saya tidak bisa menemukan detail untuk produk '{product_name_to_detail}'. Mungkin nama produknya kurang spesifik?")
                return [SlotSet("product_name_slot", None)]

            detail_url = f"{API_ROOT_URL}/product/{product_id_found}"
            print(f"Mengambil detail produk dari URL: {detail_url}")

            async with aiohttp.ClientSession() as session:
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


class ActionDefaultFallback(Action):
    def name(self) -> Text:
        return "action_default_fallback"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(template="utter_core_fallback")
        return []
