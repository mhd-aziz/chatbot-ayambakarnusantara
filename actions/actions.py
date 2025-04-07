import logging
from typing import Any, Dict, List, Optional, Text
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, FollowupAction

from db_connector import DatabaseConnector

logger = logging.getLogger(__name__)


def convert_datetimes(obj):
    """Convert datetime objects to strings to make them JSON serializable."""
    if isinstance(obj, dict):
        return {key: convert_datetimes(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_datetimes(item) for item in obj]
    elif hasattr(obj, 'strftime'):  # Check if object is datetime-like
        return obj.strftime('%Y-%m-%d %H:%M:%S')
    else:
        return obj


class ActionProductSearch(Action):
    """Action untuk mencari produk berdasarkan nama"""

    def name(self) -> Text:
        return "action_product_search"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        # Ambil entity produk dari pesan
        product_name = next(tracker.get_latest_entity_values("product"), None)

        if not product_name:
            dispatcher.utter_message(
                text=
                "Maaf, saya tidak mengerti produk apa yang Anda cari. Bisa berikan nama produknya?"
            )
            return []

        # Hubungkan ke database
        try:
            db = DatabaseConnector()
            products = db.get_products_by_name(product_name)

            if not products:
                dispatcher.utter_message(
                    text=
                    f"Maaf, saya tidak menemukan produk '{product_name}'. Coba cari dengan kata kunci lain?"
                )
                return []

            # Tampilkan hasil
            message = f"Saya menemukan {len(products)} produk untuk '{product_name}':\n\n"

            for idx, product in enumerate(products, 1):
                avg_rating = db.get_product_average_rating(product['id'])
                rating_display = f"⭐ {avg_rating:.1f}" if avg_rating else "Belum ada rating"

                message += f"{idx}. *{product['name']}*\n"
                message += f"   💰 Rp {int(product['price']):,}\n"
                message += f"   📦 Stok: {product['stock']}\n"
                message += f"   🏪 Toko: {product['shop_name']}\n"
                message += f"   {rating_display}\n\n"

            dispatcher.utter_message(text=message)

            # Set slot untuk digunakan nanti dan tanyakan apakah perlu bantuan lain
            return [
                SlotSet("search_results", products),
                FollowupAction("utter_ask_more_help")
            ]

        except Exception as e:
            logger.error(f"Error in product search: {str(e)}")
            dispatcher.utter_message(
                text=
                "Maaf, terjadi kesalahan saat mencari produk. Silakan coba lagi nanti."
            )
            return []
        finally:
            if 'db' in locals():
                db.close()


class ActionProductDetail(Action):
    """Action untuk menampilkan detail produk berdasarkan ID atau nama"""

    def name(self) -> Text:
        return "action_product_detail"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        # Ambil product_id dari slot atau entity
        product_id = tracker.get_slot("product_id")

        # Jika tidak ada di slot, coba ambil dari entity terbaru
        if not product_id:
            product_id = next(tracker.get_latest_entity_values("product_id"),
                              None)

        # Jika masih tidak ada, coba ambil nama produk
        product_name = None
        if not product_id:
            product_name = next(tracker.get_latest_entity_values("product"),
                                None)

        if not product_id and not product_name:
            dispatcher.utter_message(
                text=
                "Maaf, saya tidak tahu produk mana yang ingin Anda lihat detailnya. Bisa sebutkan ID atau nama produknya?"
            )
            return []

        # Hubungkan ke database
        try:
            db = DatabaseConnector()
            product = None

            # Jika ada ID, gunakan ID
            if product_id:
                product = db.get_product_by_id(product_id)
                if not product:
                    dispatcher.utter_message(
                        text=
                        f"Maaf, saya tidak menemukan produk dengan ID {product_id}."
                    )
                    return []

            # Jika ada nama produk
            elif product_name:
                logger.info(f"Mencari produk dengan nama: {product_name}")

                # 1. Coba cari dengan exact match terlebih dahulu
                exact_product = db.get_product_by_name(product_name)
                if exact_product:
                    logger.info(
                        f"Ditemukan produk dengan exact match: {exact_product['name']}"
                    )
                    product = exact_product
                    product_id = product['id']
                else:
                    # 2. Jika tidak ada exact match, cari dengan metode get_products_by_name
                    products = db.get_products_by_name(product_name)

                    if not products:
                        # 3. Jika masih tidak ada, coba pencarian lebih luas
                        products = db.search_products_full(product_name)

                    if products:
                        # Evaluasi relevance score antar produk
                        best_match = None
                        highest_score = -1

                        for p in products:
                            # Bandingkan nama produk dengan query
                            product_lower = p['name'].lower()
                            query_lower = product_name.lower()

                            # Hitung score sederhana
                            score = 0

                            # Exact match mendapat score tertinggi
                            if product_lower == query_lower:
                                score = 100
                            # Startswith mendapat score tinggi
                            elif product_lower.startswith(query_lower):
                                score = 80
                            # Contains mendapat score menengah
                            elif query_lower in product_lower:
                                score = 60
                            # Partial word match
                            else:
                                # Hitung berapa kata yang cocok
                                query_words = query_lower.split()
                                product_words = product_lower.split()

                                matching_words = sum(
                                    1 for w in query_words
                                    if any(w in pw for pw in product_words))
                                score = (matching_words /
                                         len(query_words)) * 50

                            # Faktor rating juga mempengaruhi score (bobot lebih kecil)
                            if 'average_rating' in p and p['average_rating']:
                                score += min(p['average_rating'] * 2,
                                             10)  # max +10 points for rating

                            logger.info(f"Produk: {p['name']}, Score: {score}")

                            if score > highest_score:
                                highest_score = score
                                best_match = p

                        if best_match:
                            product = best_match
                            product_id = product['id']
                            logger.info(
                                f"Produk terbaik: {product['name']} dengan score {highest_score}"
                            )
                        else:
                            dispatcher.utter_message(
                                text=
                                f"Maaf, saya tidak menemukan produk yang sesuai dengan '{product_name}'."
                            )
                            return []
                    else:
                        dispatcher.utter_message(
                            text=
                            f"Maaf, saya tidak menemukan produk dengan nama '{product_name}'."
                        )
                        return []

            # Ambil rating produk
            avg_rating = db.get_product_average_rating(product_id)
            ratings = db.get_product_ratings(product_id)

            # Buat pesan detail produk
            message = f"*{product['name']}*\n\n"
            message += f"💰 Harga: Rp {int(product['price']):,}\n"
            message += f"📦 Stok: {product['stock']}\n"
            message += f"🏪 Toko: {product['shop_name']}\n"

            if avg_rating:
                message += f"⭐ Rating: {avg_rating:.1f}/5.0 ({len(ratings)} ulasan)\n\n"
            else:
                message += "⭐ Belum ada rating\n\n"

            message += f"📝 *Deskripsi*:\n{product['description']}\n\n"

            # Tambahkan beberapa ulasan teratas jika ada
            if ratings:
                message += "*Ulasan Pembeli*:\n"
                for idx, rating in enumerate(ratings[:3], 1):
                    message += f"{idx}. ⭐ {rating['value']}/5 - {rating['username']}\n"
                    if rating['comment']:
                        message += f"   \"{rating['comment']}\"\n"

            dispatcher.utter_message(text=message)
            product = convert_datetimes(product)
            ratings = convert_datetimes(ratings)
            return [
                SlotSet("current_product", product),
                SlotSet("product_id", product_id),
                FollowupAction("utter_ask_more_help")
            ]

        except Exception as e:
            logger.error(f"Error in product detail: {str(e)}")
            dispatcher.utter_message(
                text=
                "Maaf, terjadi kesalahan saat mencari detail produk. Silakan coba lagi nanti."
            )
            return []
        finally:
            if 'db' in locals():
                db.close()


class ActionListTopProducts(Action):
    """Action untuk menampilkan produk teratas"""

    def name(self) -> Text:
        return "action_list_top_products"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        try:
            # Initialize products to None to avoid reference errors
            products = None

            db = DatabaseConnector()
            top_products = db.get_top_rated_products(limit=5)

            if not top_products:
                # Jika tidak ada produk dengan rating, tampilkan produk terbaru
                products = db.get_all_products(limit=5)

                if not products:
                    dispatcher.utter_message(
                        text=
                        "Maaf, sepertinya belum ada produk yang tersedia saat ini."
                    )
                    return []

                message = "Berikut adalah produk terbaru kami:\n\n"

                for idx, product in enumerate(products, 1):
                    message += f"{idx}. *{product['name']}*\n"
                    message += f"   💰 Rp {int(product['price']):,}\n"
                    message += f"   🏪 Toko: {product['shop_name']}\n\n"
            else:
                message = "Berikut adalah produk dengan rating tertinggi:\n\n"

                for idx, product in enumerate(top_products, 1):
                    message += f"{idx}. *{product['name']}*\n"
                    message += f"   💰 Rp {int(product['price']):,}\n"
                    message += f"   ⭐ {product['average_rating']:.1f}/5.0 ({product['rating_count']} ulasan)\n"
                    message += f"   🏪 Toko: {product['shop_name']}\n\n"

            dispatcher.utter_message(text=message)

            # Only convert products if they exist
            if top_products:
                top_products = convert_datetimes(top_products)
            if products:
                products = convert_datetimes(products)

            return [
                SlotSet(
                    "top_products", top_products if top_products else
                    (products if products else [])),
                FollowupAction("utter_ask_more_help")
            ]

        except Exception as e:
            logger.error(f"Error listing top products: {str(e)}")
            dispatcher.utter_message(
                text=
                "Maaf, terjadi kesalahan saat mengambil daftar produk. Silakan coba lagi nanti."
            )
            return []
        finally:
            if 'db' in locals():
                db.close()


class ActionCheckOrderStatus(Action):
    """Action untuk cek status pesanan"""

    def name(self) -> Text:
        return "action_check_order_status"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        # Ambil order_id dari slot atau entity
        order_id = tracker.get_slot("order_id")

        # Jika tidak ada di slot, coba ambil dari entity terbaru
        if not order_id:
            order_id = next(tracker.get_latest_entity_values("order_id"), None)

        if not order_id:
            dispatcher.utter_message(response="utter_ask_order_id")
            return []

        try:
            # Convert to integer if it's a string
            if isinstance(order_id, str) and order_id.isdigit():
                order_id = int(order_id)

            db = DatabaseConnector()
            order = db.get_order_by_id(order_id)

            if not order:
                dispatcher.utter_message(
                    text=
                    f"Maaf, saya tidak menemukan pesanan dengan nomor {order_id}. Mohon periksa kembali nomor pesanan Anda."
                )
                return []

            # Ambil info pembayaran
            payment = db.get_payment_by_order_id(order_id)

            # Buat pesan status pesanan
            message = f"📋 *Informasi Pesanan #{order_id}*\n\n"
            message += f"👤 Pemesan: {order['fullName']} (@{order['username']})\n"
            message += f"💰 Total: Rp {int(order['totalAmount']):,}\n"
            message += f"📅 Tanggal: {order['createdAt'].strftime('%d %b %Y, %H:%M')}\n"
            message += f"🚩 Status: {order['status'].upper()}\n\n"

            if payment:
                message += "*Informasi Pembayaran*:\n"
                message += f"💳 Metode: {payment['paymentType'] or 'Belum dipilih'}\n"

                if payment['vaNumber']:
                    message += f"🔢 VA Number: {payment['vaNumber']}\n"

                message += f"🚩 Status Pembayaran: {payment['status'].upper()}\n"

                if payment['expiryTime']:
                    message += f"⏰ Batas Waktu: {payment['expiryTime'].strftime('%d %b %Y, %H:%M')}\n\n"

            # Tambahkan item pesanan
            if 'items' in order and order['items']:
                message += "*Item Pesanan*:\n"
                for idx, item in enumerate(order['items'], 1):
                    message += f"{idx}. {item['product_name']} ({item['quantity']} x Rp {int(item['price']):,})\n"

            dispatcher.utter_message(text=message)
            order = convert_datetimes(order)
            payment = convert_datetimes(payment)
            # Simpan order_id dan tanyakan jika perlu bantuan lain
            return [
                SlotSet("order_id", order_id),
                FollowupAction("utter_ask_more_help")
            ]

        except Exception as e:
            logger.error(f"Error checking order status: {str(e)}")
            dispatcher.utter_message(
                text=
                "Maaf, terjadi kesalahan saat mengecek status pesanan. Silakan coba lagi nanti."
            )
            return []
        finally:
            if 'db' in locals():
                db.close()


class ActionCheckPaymentStatus(Action):
    """Action untuk cek status pembayaran"""

    def name(self) -> Text:
        return "action_check_payment_status"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        # Ambil order_id dari slot atau entity
        order_id = tracker.get_slot("order_id")

        # Jika tidak ada di slot, coba ambil dari entity terbaru
        if not order_id:
            order_id = next(tracker.get_latest_entity_values("order_id"), None)

        if not order_id:
            dispatcher.utter_message(response="utter_ask_order_id")
            return []

        try:
            # Convert to integer if it's a string
            if isinstance(order_id, str) and order_id.isdigit():
                order_id = int(order_id)

            db = DatabaseConnector()
            payment_status = db.get_payment_status(order_id)

            if not payment_status:
                dispatcher.utter_message(
                    text=
                    f"Maaf, saya tidak menemukan informasi pembayaran untuk pesanan #{order_id}. Mohon periksa kembali nomor pesanan Anda."
                )
                return []

            # Ambil info pembayaran lengkap
            payment = db.get_payment_by_order_id(order_id)

            # Sesuaikan pesan berdasarkan status
            status_map = {
                "pending": "Menunggu Pembayaran",
                "success": "Pembayaran Berhasil",
                "failed": "Pembayaran Gagal",
                "expired": "Pembayaran Kedaluwarsa",
                "canceled": "Pembayaran Dibatalkan"
            }

            payment_status_text = status_map.get(
                payment_status['status'], payment_status['status'].upper())

            message = f"💳 *Status Pembayaran Pesanan #{order_id}*\n\n"
            message += f"Status: {payment_status_text}\n"

            if payment:
                if payment['paymentType']:
                    message += f"Metode: {payment['paymentType']}\n"

                if payment['amount']:
                    message += f"Jumlah: Rp {int(payment['amount']):,}\n"

                if payment['vaNumber']:
                    message += f"Nomor VA: {payment['vaNumber']}\n"

                if payment['expiryTime'] and payment_status[
                        'status'] == 'pending':
                    message += f"Batas Waktu: {payment['expiryTime'].strftime('%d %b %Y, %H:%M')}\n"

            dispatcher.utter_message(text=message)
            payment_status = convert_datetimes(payment_status)
            payment = convert_datetimes(payment)
            # Simpan order_id dan tanyakan jika perlu bantuan lain
            return [
                SlotSet("order_id", order_id),
                FollowupAction("utter_ask_more_help")
            ]

        except Exception as e:
            logger.error(f"Error checking payment status: {str(e)}")
            dispatcher.utter_message(
                text=
                "Maaf, terjadi kesalahan saat mengecek status pembayaran. Silakan coba lagi nanti."
            )
            return []
        finally:
            if 'db' in locals():
                db.close()


class ActionAddRating(Action):
    """Action untuk menambahkan rating produk"""

    def name(self) -> Text:
        return "action_add_rating"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        # Ambil informasi yang diperlukan dari slot dan entity
        user_id = tracker.get_slot("user_id")
        product_id = tracker.get_slot("product_id")
        rating_value = tracker.get_slot("rating_value")
        rating_comment = tracker.get_slot("rating_comment")

        # Jika tidak ada di slot, coba ambil dari entity terbaru
        if not product_id:
            product_id = next(tracker.get_latest_entity_values("product_id"),
                              None)

        if not rating_value:
            rating_value = next(
                tracker.get_latest_entity_values("rating_value"), None)

        # Validasi input
        if not user_id:
            dispatcher.utter_message(response="utter_login_required")
            return [FollowupAction("utter_redirect_login")]

        if not product_id:
            dispatcher.utter_message(response="utter_ask_product_id")
            return []

        if not rating_value:
            dispatcher.utter_message(response="utter_ask_rating_value")
            return []

        # Konversi nilai rating jika perlu
        try:
            if isinstance(rating_value, str) and rating_value.isdigit():
                rating_value = int(rating_value)

            if not 1 <= rating_value <= 5:
                dispatcher.utter_message(
                    text=
                    "Rating harus bernilai antara 1 sampai 5. Silakan berikan rating yang valid."
                )
                return []
        except:
            dispatcher.utter_message(
                text=
                "Rating harus bernilai antara 1 sampai 5. Silakan berikan rating yang valid."
            )
            return []

        try:
            db = DatabaseConnector()

            # Pastikan produk ada
            product = db.get_product_by_id(product_id)
            if not product:
                dispatcher.utter_message(
                    text=f"Maaf, produk dengan ID {product_id} tidak ditemukan."
                )
                return []

            # Tambahkan rating
            success = db.add_product_rating(user_id, product_id, rating_value,
                                            rating_comment)

            if success:
                star_emoji = "⭐" * rating_value
                message = f"Terima kasih! Anda telah memberikan rating {star_emoji} untuk produk *{product['name']}*."

                if rating_comment:
                    message += f"\n\nUlasan Anda: \"{rating_comment}\""
                    dispatcher.utter_message(text=message)
                    return [
                        SlotSet("rating_value", None),
                        SlotSet("rating_comment", None),
                        # Set the conversation stage to post_rating
                        SlotSet("conversation_stage", "post_rating"),
                        FollowupAction("action_thank_for_review")
                    ]
                else:
                    dispatcher.utter_message(text=message)
                    return [
                        SlotSet("rating_value", None),
                        # Set the conversation stage to post_rating
                        SlotSet("conversation_stage", "post_rating"),
                        FollowupAction("utter_ask_rating_comment")
                    ]
            else:
                dispatcher.utter_message(
                    text=
                    "Maaf, terjadi kesalahan saat menyimpan rating Anda. Silakan coba lagi nanti."
                )
                return []

        except Exception as e:
            logger.error(f"Error adding rating: {str(e)}")
            dispatcher.utter_message(
                text=
                "Maaf, terjadi kesalahan saat menyimpan rating. Silakan coba lagi nanti."
            )
            return []
        finally:
            if 'db' in locals():
                db.close()

    """Action untuk menambahkan rating produk"""

    def name(self) -> Text:
        return "action_add_rating"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        # Ambil informasi yang diperlukan dari slot dan entity
        user_id = tracker.get_slot("user_id")
        product_id = tracker.get_slot("product_id")
        rating_value = tracker.get_slot("rating_value")
        rating_comment = tracker.get_slot("rating_comment")

        # Jika tidak ada di slot, coba ambil dari entity terbaru
        if not product_id:
            product_id = next(tracker.get_latest_entity_values("product_id"),
                              None)

        if not rating_value:
            rating_value = next(
                tracker.get_latest_entity_values("rating_value"), None)

        # Validasi input
        if not user_id:
            dispatcher.utter_message(response="utter_login_required")
            return [FollowupAction("utter_redirect_login")]

        if not product_id:
            dispatcher.utter_message(response="utter_ask_product_id")
            return []

        if not rating_value:
            dispatcher.utter_message(response="utter_ask_rating_value")
            return []

        # Konversi nilai rating jika perlu
        try:
            if isinstance(rating_value, str) and rating_value.isdigit():
                rating_value = int(rating_value)

            if not 1 <= rating_value <= 5:
                dispatcher.utter_message(
                    text=
                    "Rating harus bernilai antara 1 sampai 5. Silakan berikan rating yang valid."
                )
                return []
        except:
            dispatcher.utter_message(
                text=
                "Rating harus bernilai antara 1 sampai 5. Silakan berikan rating yang valid."
            )
            return []

        try:
            db = DatabaseConnector()

            # Pastikan produk ada
            product = db.get_product_by_id(product_id)
            if not product:
                dispatcher.utter_message(
                    text=f"Maaf, produk dengan ID {product_id} tidak ditemukan."
                )
                return []

            # Tambahkan rating
            success = db.add_product_rating(user_id, product_id, rating_value,
                                            rating_comment)

            if success:
                star_emoji = "⭐" * rating_value
                message = f"Terima kasih! Anda telah memberikan rating {star_emoji} untuk produk *{product['name']}*."

                if rating_comment:
                    message += f"\n\nUlasan Anda: \"{rating_comment}\""
                    dispatcher.utter_message(text=message)
                    return [
                        SlotSet("rating_value", None),
                        SlotSet("rating_comment", None),
                        FollowupAction("action_thank_for_review")
                    ]
                else:
                    dispatcher.utter_message(text=message)
                    return [
                        SlotSet("rating_value", None),
                        FollowupAction("utter_ask_rating_comment")
                    ]
            else:
                dispatcher.utter_message(
                    text=
                    "Maaf, terjadi kesalahan saat menyimpan rating Anda. Silakan coba lagi nanti."
                )
                return []

        except Exception as e:
            logger.error(f"Error adding rating: {str(e)}")
            dispatcher.utter_message(
                text=
                "Maaf, terjadi kesalahan saat menyimpan rating. Silakan coba lagi nanti."
            )
            return []
        finally:
            if 'db' in locals():
                db.close()


class ActionThankForReview(Action):
    """Action untuk berterima kasih atas review yang diberikan"""

    def name(self) -> Text:
        return "action_thank_for_review"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(response="utter_thank_for_review")
        return [FollowupAction("utter_ask_more_help")]


class ActionListShopProducts(Action):
    """Action untuk menampilkan produk dari toko tertentu"""

    def name(self) -> Text:
        return "action_list_shop_products"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        # Ambil shop_id dari slot atau entity
        shop_id = tracker.get_slot("shop_id")

        # Jika tidak ada di slot, coba ambil dari entity terbaru
        if not shop_id:
            shop_id = next(tracker.get_latest_entity_values("shop_id"), None)

        # Jika masih tidak ada, coba ambil nama toko
        shop_name = None
        if not shop_id:
            shop_name = next(tracker.get_latest_entity_values("shop"), None)

        if not shop_id and not shop_name:
            dispatcher.utter_message(
                text=
                "Untuk melihat produk dari toko tertentu, saya perlu tahu toko mana yang Anda maksud. Bisa sebutkan nama toko atau ID toko?"
            )
            return []

        try:
            db = DatabaseConnector()
            products = None

            # Jika ada ID, gunakan ID
            if shop_id:
                # Convert to integer if it's a string
                if isinstance(shop_id, str) and shop_id.isdigit():
                    shop_id = int(shop_id)
                products = db.get_products_by_shop(shop_id)

            # Implementasi tambahan untuk mencari berdasarkan nama toko
            # Ini memerlukan fungsi tambahan di db_connector.py
            # Tambahkan logika sesuai implementasi database Anda

            if not products:
                dispatcher.utter_message(
                    text=
                    f"Maaf, tidak ditemukan produk dari toko ini atau toko yang dimaksud tidak ada."
                )
                return []

            # Ambil rating toko
            shop_rating = db.get_shop_average_rating(
                shop_id if shop_id else None)

            # Buat pesan
            message = f"🏪 *Produk dari Toko*\n"

            if shop_rating:
                message += f"⭐ Rating Toko: {shop_rating:.1f}/5.0\n\n"
            else:
                message += "⭐ Toko belum memiliki rating\n\n"

            for idx, product in enumerate(products, 1):
                avg_rating = db.get_product_average_rating(product['id'])
                rating_display = f"⭐ {avg_rating:.1f}" if avg_rating else "Belum ada rating"

                message += f"{idx}. *{product['name']}*\n"
                message += f"   💰 Rp {int(product['price']):,}\n"
                message += f"   📦 Stok: {product['stock']}\n"
                message += f"   {rating_display}\n\n"

            dispatcher.utter_message(text=message)
            return [
                SlotSet("shop_products", products),
                SlotSet("shop_id", shop_id),
                FollowupAction("utter_ask_more_help")
            ]

        except Exception as e:
            logger.error(f"Error listing shop products: {str(e)}")
            dispatcher.utter_message(
                text=
                "Maaf, terjadi kesalahan saat mengambil daftar produk toko. Silakan coba lagi nanti."
            )
            return []
        finally:
            if 'db' in locals():
                db.close()


class ActionShowUserRatings(Action):
    """Action untuk menampilkan rating yang diberikan pengguna"""

    def name(self) -> Text:
        return "action_show_user_ratings"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        # Ambil user_id dari slot
        user_id = tracker.get_slot("user_id")

        if not user_id:
            dispatcher.utter_message(response="utter_login_required")
            return [FollowupAction("utter_redirect_login")]

        try:
            # Convert to integer if it's a string
            if isinstance(user_id, str) and user_id.isdigit():
                user_id = int(user_id)

            db = DatabaseConnector()
            ratings = db.get_user_ratings(user_id)

            if not ratings:
                dispatcher.utter_message(
                    text="Anda belum memberikan rating untuk produk apapun.")
                return [FollowupAction("utter_ask_more_help")]

            # Buat pesan
            message = "📊 *Rating yang Anda Berikan*\n\n"

            for idx, rating in enumerate(ratings, 1):
                star_emoji = "⭐" * rating['value']
                message += f"{idx}. *{rating['product_name']}*\n"
                message += f"   {star_emoji}\n"

                if rating['comment']:
                    message += f"   \"{rating['comment']}\"\n"

                message += f"   🏪 Toko: {rating['shop_name']}\n"
                message += f"   📅 {rating['createdAt'].strftime('%d %b %Y')}\n\n"

            dispatcher.utter_message(text=message)
            ratings = convert_datetimes(ratings)
            return [FollowupAction("utter_ask_more_help")]

        except Exception as e:
            logger.error(f"Error showing user ratings: {str(e)}")
            dispatcher.utter_message(
                text=
                "Maaf, terjadi kesalahan saat mengambil data rating Anda. Silakan coba lagi nanti."
            )
            return []
        finally:
            if 'db' in locals():
                db.close()


class ActionAcknowledgeAffirmation(Action):
    """Action untuk merespon afirmasi pengguna"""

    def name(self) -> Text:
        return "action_acknowledge_affirmation"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(response="utter_acknowledge_affirmation")
        return [FollowupAction("utter_help")]


class ActionAcknowledgeDenial(Action):
    """Action untuk merespon penolakan pengguna"""

    def name(self) -> Text:
        return "action_acknowledge_denial"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(response="utter_acknowledge_denial")
        return [FollowupAction("utter_goodbye")]


class ActionRedirectOrderPage(Action):
    """Action untuk mengarahkan pengguna ke halaman pemesanan untuk complex order"""

    def name(self) -> Text:
        return "action_redirect_order_page"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        # Ambil entity produk dan kuantitas jika ada
        product = next(tracker.get_latest_entity_values("product"), None)
        quantity = next(tracker.get_latest_entity_values("quantity"), None)
        spicy_level = next(tracker.get_latest_entity_values("spicy_level"),
                           None)

        message = "Untuk melakukan pemesanan kompleks dengan beberapa menu, silakan kunjungi halaman pemesanan di website atau aplikasi kami."

        if product and quantity:
            message += f"\n\nAnda ingin memesan {quantity} porsi {product}"
            if spicy_level:
                message += f" dengan level kepedasan {spicy_level}"
            message += ". Anda dapat menyelesaikan pesanan ini melalui website atau aplikasi kami."

        dispatcher.utter_message(text=message)
        return [FollowupAction("utter_ask_more_help")]
