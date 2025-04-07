import mysql.connector
import logging
import os
from typing import Dict, List, Optional, Any, Tuple
from dotenv import load_dotenv
from urllib.parse import urlparse
import time
from datetime import datetime, timedelta

# Muat file .env
load_dotenv()

# Konfigurasi logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ])
logger = logging.getLogger(__name__)


class DatabaseConnector:
    """
    Kelas untuk menghubungkan chatbot dengan database MySQL
    """

    def __init__(self, max_retries: int = 3, retry_delay: int = 5):
        """
        Inisialisasi koneksi database MySQL menggunakan DATABASE_URL
        
        Args:
            max_retries: Jumlah maksimum percobaan koneksi ulang
            retry_delay: Waktu tunggu (dalam detik) antara percobaan koneksi
        """
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.connect_to_database()

    def connect_to_database(self):
        """
        Menghubungkan ke database dengan mekanisme retry
        """
        retries = 0
        while retries < self.max_retries:
            try:
                # Ambil DATABASE_URL dari environment variable
                database_url = os.getenv("DATABASE_URL")
                if not database_url:
                    raise ValueError(
                        "DATABASE_URL tidak ditemukan dalam environment variable"
                    )

                logger.info("Parsing DATABASE_URL...")

                # Parse DATABASE_URL
                result = urlparse(database_url)
                username = result.username
                password = result.password
                hostname = result.hostname
                port = result.port or 3306

                # Ekstrak nama database dari path
                path = result.path
                database = path.strip('/')

                # Jika path berisi '?', hapus bagian setelahnya
                if '?' in database:
                    database = database.split('?')[0]

                logger.info(
                    f"Connecting to database: {database} at {hostname}:{port}")

                # Buat koneksi MySQL
                self.db = mysql.connector.connect(
                    host=hostname,
                    user=username,
                    password=password,
                    database=database,
                    port=port,
                    # Parameter koneksi yang lebih aman
                    connection_timeout=60,
                    autocommit=False,
                    buffered=True,
                    use_pure=True,
                    # Custom pool name yang lebih pendek
                    pool_name="ayambakarnusantara_pool"
                    if hostname.find(".") > 0 else None)
                self.cursor = self.db.cursor(dictionary=True)
                logger.info(
                    "MySQL database connection established successfully")
                return
            except mysql.connector.Error as e:
                retries += 1
                logger.warning(
                    f"MySQL connection attempt {retries} failed: {str(e)}")
                if retries < self.max_retries:
                    logger.info(f"Retrying in {self.retry_delay} seconds...")
                    time.sleep(self.retry_delay)
                else:
                    logger.error(
                        f"All connection attempts failed after {self.max_retries} retries"
                    )
                    raise
            except Exception as e:
                logger.error(
                    f"Unexpected error during database connection: {str(e)}")
                raise

    def reconnect_if_needed(self):
        """
        Memeriksa koneksi dan mencoba menghubungkan kembali jika terputus
        """
        try:
            if not self.db.is_connected():
                logger.warning("Database connection lost. Reconnecting...")
                self.db.reconnect(attempts=self.max_retries,
                                  delay=self.retry_delay)
                self.cursor = self.db.cursor(dictionary=True)
                logger.info("Reconnection successful")
        except Exception as e:
            logger.error(f"Reconnection failed: {str(e)}")
            self.connect_to_database()  # Coba hubungkan dari awal

    def execute_query(self,
                      query: str,
                      params: tuple = None,
                      commit: bool = False) -> Tuple[bool, Any]:
        """
        Mengeksekusi query dengan penanganan kesalahan dan reconnect
        
        Args:
            query: SQL query
            params: Parameter untuk query
            commit: True jika perlu commit setelah query
            
        Returns:
            Tuple dari (success, result)
        """
        for attempt in range(self.max_retries):
            try:
                self.reconnect_if_needed()

                self.cursor.execute(query, params)

                if commit:
                    self.db.commit()
                    return True, None
                else:
                    if query.strip().upper().startswith("SELECT"):
                        return True, self.cursor.fetchall()
                    else:
                        return True, self.cursor.lastrowid

            except mysql.connector.Error as e:
                logger.error(
                    f"Database error on attempt {attempt+1}: {str(e)}")
                if "Connection" in str(e) and attempt < self.max_retries - 1:
                    self.reconnect_if_needed()
                    time.sleep(self.retry_delay)
                else:
                    if commit:
                        self.db.rollback()
                    return False, str(e)
            except Exception as e:
                logger.error(f"Unexpected error: {str(e)}")
                if commit:
                    self.db.rollback()
                return False, str(e)

        return False, "Maximum retry attempts exceeded"

    # === PRODUCT METHODS ===

    def get_product_by_id(self, product_id: int) -> Optional[Dict[str, Any]]:
        """
        Mendapatkan informasi produk berdasarkan ID
        """
        try:
            self.reconnect_if_needed()
            query = """
            SELECT p.id, p.name, p.description, p.price, p.stock, p.photoProduct,
                   s.name as shop_name, s.id as shopId, p.createdAt, p.updatedAt
            FROM Product p
            JOIN Shop s ON p.shopId = s.id
            WHERE p.id = %s
            """
            self.cursor.execute(query, (product_id, ))
            product = self.cursor.fetchone()

            if product:
                # Tambahkan informasi rating jika ada
                avg_rating = self.get_product_average_rating(product_id)
                if avg_rating:
                    product['average_rating'] = avg_rating
                else:
                    product['average_rating'] = 0.0

                # Tambahkan jumlah rating
                product['rating_count'] = self.get_product_rating_count(
                    product_id)

            return product
        except Exception as e:
            logger.error(f"Error fetching product by ID: {str(e)}")
            return None

    def get_product_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Mendapatkan produk dengan nama yang persis sama (exact match)
        """
        try:
            self.reconnect_if_needed()
            query = """
            SELECT p.id, p.name, p.description, p.price, p.stock, p.photoProduct,
                   s.name as shop_name, s.id as shopId, p.createdAt, p.updatedAt,
                   COALESCE((SELECT AVG(r.value) FROM Rating r WHERE r.productId = p.id), 0) as average_rating,
                   (SELECT COUNT(r.id) FROM Rating r WHERE r.productId = p.id) as rating_count
            FROM Product p
            JOIN Shop s ON p.shopId = s.id
            WHERE LOWER(p.name) = LOWER(%s)
            LIMIT 1
            """
            self.cursor.execute(query, (name, ))
            product = self.cursor.fetchone()
            return product
        except Exception as e:
            logger.error(f"Error fetching product by exact name: {str(e)}")
            return None

    def get_products_by_name(self,
                             name: str,
                             limit: int = 10,
                             offset: int = 0) -> List[Dict[str, Any]]:
        """
        Mencari produk berdasarkan nama (penelusuran parsial)
        
        Args:
            name: String pencarian nama produk
            limit: Batas jumlah hasil
            offset: Offset untuk pagination
        """
        try:
            self.reconnect_if_needed()
            # Search dengan prioritas pada exact match
            query = """
            SELECT p.id, p.name, p.description, p.price, p.stock, p.photoProduct,
                   s.name as shop_name, s.id as shopId,
                   COALESCE((SELECT AVG(r.value) FROM Rating r WHERE r.productId = p.id), 0) as average_rating,
                   (SELECT COUNT(r.id) FROM Rating r WHERE r.productId = p.id) as rating_count,
                   CASE 
                       WHEN LOWER(p.name) = LOWER(%s) THEN 1
                       WHEN p.name LIKE CONCAT(%s, '%%') THEN 2
                       WHEN p.name LIKE CONCAT('%%', %s, '%%') THEN 3
                       ELSE 4
                   END as match_priority
            FROM Product p
            JOIN Shop s ON p.shopId = s.id
            WHERE p.name LIKE %s
            ORDER BY match_priority, p.stock > 0 DESC, average_rating DESC
            LIMIT %s OFFSET %s
            """
            self.cursor.execute(query,
                                (name, name, name, f"%{name}%", limit, offset))
            products = self.cursor.fetchall()
            return products
        except Exception as e:
            logger.error(f"Error searching products by name: {str(e)}")
            return []

    def get_all_products(self,
                         limit: int = 10,
                         offset: int = 0,
                         sort_by: str = "newest") -> List[Dict[str, Any]]:
        """
        Mendapatkan semua produk dengan batas jumlah
        
        Args:
            limit: Batas jumlah hasil
            offset: Offset untuk pagination
            sort_by: Metode pengurutan ('newest', 'price_low', 'price_high', 'rating')
        """
        try:
            self.reconnect_if_needed()
            # Tentukan order by clause berdasarkan sort_by
            if sort_by == "price_low":
                order_clause = "p.price ASC"
            elif sort_by == "price_high":
                order_clause = "p.price DESC"
            elif sort_by == "rating":
                order_clause = "average_rating DESC, rating_count DESC"
            else:  # default to newest
                order_clause = "p.createdAt DESC"

            query = f"""
            SELECT p.id, p.name, p.description, p.price, p.stock, p.photoProduct,
                   s.name as shop_name, s.id as shopId,
                   COALESCE((SELECT AVG(r.value) FROM Rating r WHERE r.productId = p.id), 0) as average_rating,
                   (SELECT COUNT(r.id) FROM Rating r WHERE r.productId = p.id) as rating_count
            FROM Product p
            JOIN Shop s ON p.shopId = s.id
            ORDER BY p.stock > 0 DESC, {order_clause}
            LIMIT %s OFFSET %s
            """
            self.cursor.execute(query, (limit, offset))
            products = self.cursor.fetchall()
            return products
        except Exception as e:
            logger.error(f"Error fetching all products: {str(e)}")
            return []

    def get_products_by_shop(self,
                             shop_id: int,
                             limit: int = 10,
                             offset: int = 0) -> List[Dict[str, Any]]:
        """
        Mendapatkan produk berdasarkan ID toko
        
        Args:
            shop_id: ID toko
            limit: Batas jumlah hasil
            offset: Offset untuk pagination
        """
        try:
            self.reconnect_if_needed()
            query = """
            SELECT p.id, p.name, p.description, p.price, p.stock, p.photoProduct,
                   COALESCE((SELECT AVG(r.value) FROM Rating r WHERE r.productId = p.id), 0) as average_rating,
                   (SELECT COUNT(r.id) FROM Rating r WHERE r.productId = p.id) as rating_count
            FROM Product p
            WHERE p.shopId = %s
            ORDER BY p.createdAt DESC
            LIMIT %s OFFSET %s
            """
            self.cursor.execute(query, (shop_id, limit, offset))
            products = self.cursor.fetchall()
            return products
        except Exception as e:
            logger.error(f"Error fetching products by shop: {str(e)}")
            return []

    def search_products_full(self,
                             query_text: str,
                             limit: int = 10) -> List[Dict[str, Any]]:
        """
        Pencarian produk lengkap dengan berbagai parameter
        
        Args:
            query_text: Teks pencarian
            limit: Batas jumlah hasil
        """
        try:
            self.reconnect_if_needed()

            # Parsing query untuk mendapatkan product name
            query_params = query_text.lower().split()
            search_terms = '%' + '%'.join(query_params) + '%'

            query = """
            SELECT p.id, p.name, p.description, p.price, p.stock, p.photoProduct,
                   s.name as shop_name, s.id as shopId,
                   COALESCE((SELECT AVG(r.value) FROM Rating r WHERE r.productId = p.id), 0) as average_rating,
                   (SELECT COUNT(r.id) FROM Rating r WHERE r.productId = p.id) as rating_count,
                   CASE 
                      WHEN LOWER(p.name) = LOWER(%s) THEN 1
                      WHEN p.name LIKE CONCAT(%s, '%%') THEN 2
                      WHEN p.name LIKE CONCAT('%%', %s, '%%') THEN 3
                      WHEN p.description LIKE CONCAT('%%', %s, '%%') THEN 4
                      ELSE 5
                   END as relevance
            FROM Product p
            JOIN Shop s ON p.shopId = s.id
            WHERE LOWER(p.name) LIKE %s 
               OR LOWER(p.description) LIKE %s
            ORDER BY relevance, p.stock > 0 DESC, average_rating DESC
            LIMIT %s
            """
            params = (query_text, query_text, query_text, query_text,
                      f"%{query_text}%", f"%{query_text}%", limit)
            self.cursor.execute(query, params)
            products = self.cursor.fetchall()
            return products
        except Exception as e:
            logger.error(f"Error in full product search: {str(e)}")
            return []

    def get_product_rating_count(self, product_id: int) -> int:
        """
        Mendapatkan jumlah rating untuk produk tertentu
        """
        try:
            self.reconnect_if_needed()
            query = """
            SELECT COUNT(*) as rating_count
            FROM Rating
            WHERE productId = %s
            """
            self.cursor.execute(query, (product_id, ))
            result = self.cursor.fetchone()
            if result:
                return int(result['rating_count'])
            return 0
        except Exception as e:
            logger.error(f"Error fetching rating count for product: {str(e)}")
            return 0

    # === ORDER METHODS ===

    def get_order_by_id(self, order_id: int) -> Optional[Dict[str, Any]]:
        """
        Mendapatkan informasi order berdasarkan ID
        """
        try:
            self.reconnect_if_needed()
            query = """
            SELECT o.id, o.userId, o.totalAmount, o.status, o.createdAt, o.updatedAt,
                   u.username, u.fullName, u.email, u.phoneNumber, u.address
            FROM `Order` o
            JOIN User u ON o.userId = u.id
            WHERE o.id = %s
            """
            self.cursor.execute(query, (order_id, ))
            order = self.cursor.fetchone()

            if order:
                # Ambil juga order items
                query_items = """
                SELECT oi.id, oi.productId, oi.quantity, oi.price,
                       p.name as product_name, p.photoProduct
                FROM OrderItem oi
                JOIN Product p ON oi.productId = p.id
                WHERE oi.orderId = %s
                """
                self.cursor.execute(query_items, (order_id, ))
                order_items = self.cursor.fetchall()
                order['items'] = order_items

                # Ambil informasi pembayaran jika ada
                payment = self.get_payment_by_order_id(order_id)
                if payment:
                    order['payment'] = payment

            return order
        except Exception as e:
            logger.error(f"Error fetching order by ID: {str(e)}")
            return None

    def get_order_status(self, order_id: int) -> Optional[str]:
        """
        Mendapatkan status pesanan berdasarkan ID
        """
        try:
            self.reconnect_if_needed()
            query = "SELECT status FROM `Order` WHERE id = %s"
            self.cursor.execute(query, (order_id, ))
            order = self.cursor.fetchone()

            if order:
                return order['status']
            return None
        except Exception as e:
            logger.error(f"Error fetching order status: {str(e)}")
            return None

    def get_recent_orders(self,
                          limit: int = 10,
                          offset: int = 0) -> List[Dict[str, Any]]:
        """
        Mendapatkan daftar pesanan terbaru
        """
        try:
            self.reconnect_if_needed()
            query = """
            SELECT o.id, o.totalAmount, o.status, o.createdAt,
                   u.username, u.fullName, u.email,
                   COUNT(oi.id) as total_items
            FROM `Order` o
            JOIN User u ON o.userId = u.id
            JOIN OrderItem oi ON o.id = oi.orderId
            GROUP BY o.id, o.totalAmount, o.status, o.createdAt, u.username, u.fullName, u.email
            ORDER BY o.createdAt DESC
            LIMIT %s OFFSET %s
            """
            self.cursor.execute(query, (limit, offset))
            orders = self.cursor.fetchall()
            return orders
        except Exception as e:
            logger.error(f"Error fetching recent orders: {str(e)}")
            return []

    def get_user_orders(self,
                        user_id: int,
                        limit: int = 10,
                        offset: int = 0) -> List[Dict[str, Any]]:
        """
        Mendapatkan pesanan dari pengguna tertentu
        """
        try:
            self.reconnect_if_needed()
            query = """
            SELECT o.id, o.totalAmount, o.status, o.createdAt, o.updatedAt,
                   COUNT(oi.id) as total_items,
                   MAX(p.status) as payment_status
            FROM `Order` o
            JOIN OrderItem oi ON o.id = oi.orderId
            LEFT JOIN Payment p ON o.id = p.orderId
            WHERE o.userId = %s
            GROUP BY o.id, o.totalAmount, o.status, o.createdAt, o.updatedAt
            ORDER BY o.createdAt DESC
            LIMIT %s OFFSET %s
            """
            self.cursor.execute(query, (user_id, limit, offset))
            orders = self.cursor.fetchall()
            return orders
        except Exception as e:
            logger.error(f"Error fetching user orders: {str(e)}")
            return []

    # === PAYMENT METHODS ===

    def get_payment_by_order_id(self,
                                order_id: int) -> Optional[Dict[str, Any]]:
        """
        Mendapatkan informasi pembayaran berdasarkan ID pesanan
        """
        try:
            self.reconnect_if_needed()
            query = """
            SELECT p.id, p.orderId, p.amount, p.paymentType, p.vaNumber,
                   p.status, p.statusOrder, p.createdAt, p.expiryTime
            FROM Payment p
            WHERE p.orderId = %s
            """
            self.cursor.execute(query, (order_id, ))
            payment = self.cursor.fetchone()

            if payment and payment['expiryTime']:
                # Periksa apakah pembayaran telah kedaluwarsa
                expired = False
                if isinstance(payment['expiryTime'], datetime):
                    now = datetime.now()
                    if now > payment['expiryTime'] and payment[
                            'status'] != 'paid':
                        expired = True
                payment['is_expired'] = expired

            return payment
        except Exception as e:
            logger.error(f"Error fetching payment by order ID: {str(e)}")
            return None

    def get_payment_status(self, order_id: int) -> Optional[Dict[str, str]]:
        """
        Mendapatkan status pembayaran berdasarkan ID pesanan
        """
        try:
            self.reconnect_if_needed()
            query = """
            SELECT status, statusOrder, expiryTime, createdAt
            FROM Payment 
            WHERE orderId = %s
            """
            self.cursor.execute(query, (order_id, ))
            payment = self.cursor.fetchone()

            if payment:
                result = {
                    'status': payment['status'],
                    'statusOrder': payment['statusOrder']
                }

                # Tambahkan info kedaluwarsa jika ada
                if payment['expiryTime'] and isinstance(
                        payment['expiryTime'], datetime):
                    now = datetime.now()
                    if now > payment['expiryTime'] and payment[
                            'status'] != 'paid':
                        result['is_expired'] = True
                    else:
                        result['is_expired'] = False

                    # Hitung waktu tersisa dalam format yang ramah
                    if not result['is_expired'] and payment['status'] != 'paid':
                        remaining = payment['expiryTime'] - now
                        hours, remainder = divmod(remaining.seconds, 3600)
                        minutes, seconds = divmod(remainder, 60)
                        result[
                            'time_remaining'] = f"{hours}:{minutes:02d}:{seconds:02d}"

                return result
            return None
        except Exception as e:
            logger.error(f"Error fetching payment status: {str(e)}")
            return None

    # === RATING METHODS ===

    def get_product_ratings(self,
                            product_id: int,
                            limit: int = 10,
                            offset: int = 0) -> List[Dict[str, Any]]:
        """
        Mendapatkan semua rating untuk produk tertentu
        """
        try:
            self.reconnect_if_needed()
            query = """
            SELECT r.id, r.value, r.comment, r.createdAt, r.updatedAt,
                u.id as userId, u.username, u.fullName, u.photoUser
            FROM Rating r
            JOIN User u ON r.userId = u.id
            WHERE r.productId = %s
            ORDER BY r.createdAt DESC
            LIMIT %s OFFSET %s
            """
            self.cursor.execute(query, (product_id, limit, offset))
            ratings = self.cursor.fetchall()
            return ratings
        except Exception as e:
            logger.error(f"Error fetching ratings for product: {str(e)}")
            return []

    def get_product_average_rating(self, product_id: int) -> Optional[float]:
        """
        Mendapatkan rata-rata rating untuk produk tertentu
        """
        try:
            self.reconnect_if_needed()
            query = """
            SELECT AVG(value) as average_rating
            FROM Rating
            WHERE productId = %s
            """
            self.cursor.execute(query, (product_id, ))
            result = self.cursor.fetchone()
            if result and result['average_rating'] is not None:
                return float(result['average_rating'])
            return None
        except Exception as e:
            logger.error(
                f"Error fetching average rating for product: {str(e)}")
            return None

    def get_shop_average_rating(self, shop_id: int) -> Optional[float]:
        """
        Mendapatkan rata-rata rating untuk semua produk dari toko tertentu
        """
        try:
            self.reconnect_if_needed()
            query = """
            SELECT AVG(r.value) as average_rating
            FROM Rating r
            JOIN Product p ON r.productId = p.id
            WHERE p.shopId = %s
            """
            self.cursor.execute(query, (shop_id, ))
            result = self.cursor.fetchone()
            if result and result['average_rating'] is not None:
                return float(result['average_rating'])
            return None
        except Exception as e:
            logger.error(f"Error fetching average rating for shop: {str(e)}")
            return None

    def add_product_rating(self,
                           user_id: int,
                           product_id: int,
                           rating_value: int,
                           comment: Optional[str] = None) -> bool:
        """
        Menambahkan atau memperbarui rating produk
        """
        try:
            self.reconnect_if_needed()
            # Cek apakah rating sudah ada
            check_query = """
            SELECT id FROM Rating
            WHERE userId = %s AND productId = %s
            """
            self.cursor.execute(check_query, (user_id, product_id))
            existing_rating = self.cursor.fetchone()

            if existing_rating:
                # Update rating yang sudah ada
                update_query = """
                UPDATE Rating
                SET value = %s, comment = %s, updatedAt = NOW()
                WHERE id = %s
                """
                self.cursor.execute(
                    update_query,
                    (rating_value, comment, existing_rating['id']))
            else:
                # Buat rating baru
                insert_query = """
                INSERT INTO Rating (value, comment, userId, productId, createdAt, updatedAt)
                VALUES (%s, %s, %s, %s, NOW(), NOW())
                """
                self.cursor.execute(
                    insert_query, (rating_value, comment, user_id, product_id))

            self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Error adding/updating product rating: {str(e)}")
            self.db.rollback()
            return False

    def get_user_ratings(self,
                         user_id: int,
                         limit: int = 10,
                         offset: int = 0) -> List[Dict[str, Any]]:
        """
        Mendapatkan semua rating yang dibuat oleh pengguna tertentu
        """
        try:
            self.reconnect_if_needed()
            query = """
            SELECT r.id, r.value, r.comment, r.createdAt, r.updatedAt,
                p.id as productId, p.name as product_name, p.photoProduct,
                s.id as shopId, s.name as shop_name
            FROM Rating r
            JOIN Product p ON r.productId = p.id
            JOIN Shop s ON p.shopId = s.id
            WHERE r.userId = %s
            ORDER BY r.createdAt DESC
            LIMIT %s OFFSET %s
            """
            self.cursor.execute(query, (user_id, limit, offset))
            ratings = self.cursor.fetchall()
            return ratings
        except Exception as e:
            logger.error(f"Error fetching user ratings: {str(e)}")
            return []

    def get_top_rated_products(self,
                               limit: int = 10,
                               min_ratings: int = 3) -> List[Dict[str, Any]]:
        """
        Mendapatkan produk dengan rating tertinggi
        
        Args:
            limit: Batas jumlah hasil
            min_ratings: Jumlah minimum rating yang harus dimiliki produk
        """
        try:
            self.reconnect_if_needed()
            query = """
            SELECT p.id, p.name, p.description, p.price, p.stock, p.photoProduct,
                s.id as shopId, s.name as shop_name, 
                AVG(r.value) as average_rating, 
                COUNT(r.id) as rating_count
            FROM Product p
            JOIN Shop s ON p.shopId = s.id
            JOIN Rating r ON p.id = r.productId
            GROUP BY p.id, p.name, p.description, p.price, p.stock, p.photoProduct, s.id, s.name
            HAVING COUNT(r.id) >= %s AND p.stock > 0
            ORDER BY average_rating DESC, rating_count DESC
            LIMIT %s
            """
            self.cursor.execute(query, (min_ratings, limit))
            products = self.cursor.fetchall()
            return products
        except Exception as e:
            logger.error(f"Error fetching top rated products: {str(e)}")
            return []

    # === SHOP METHODS ===

    def get_shop_by_id(self, shop_id: int) -> Optional[Dict[str, Any]]:
        """
        Mendapatkan informasi toko berdasarkan ID
        """
        try:
            self.reconnect_if_needed()
            query = """
            SELECT s.id, s.name, s.address, s.photoShop, s.createdAt, s.updatedAt,
                   a.id as adminId, a.username as admin_username
            FROM Shop s
            JOIN Admin a ON s.adminId = a.id
            WHERE s.id = %s
            """
            self.cursor.execute(query, (shop_id, ))
            shop = self.cursor.fetchone()

            if shop:
                # Tambahkan rating toko
                avg_rating = self.get_shop_average_rating(shop_id)
                if avg_rating:
                    shop['average_rating'] = avg_rating
                else:
                    shop['average_rating'] = 0.0

                # Hitung jumlah produk
                query_product_count = """
                SELECT COUNT(*) as product_count
                FROM Product
                WHERE shopId = %s
                """
                self.cursor.execute(query_product_count, (shop_id, ))
                result = self.cursor.fetchone()
                if result:
                    shop['product_count'] = result['product_count']
                else:
                    shop['product_count'] = 0

            return shop
        except Exception as e:
            logger.error(f"Error fetching shop by ID: {str(e)}")
            return None

    def get_shop_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Mendapatkan toko berdasarkan nama
        """
        try:
            self.reconnect_if_needed()
            query = """
            SELECT s.id, s.name, s.address, s.photoShop, s.createdAt, s.updatedAt,
                   a.id as adminId, a.username as admin_username
            FROM Shop s
            JOIN Admin a ON s.adminId = a.id
            WHERE LOWER(s.name) LIKE LOWER(%s)
            LIMIT 1
            """
            self.cursor.execute(query, (f"%{name}%", ))
            shop = self.cursor.fetchone()

            if shop:
                # Tambahkan rating toko
                avg_rating = self.get_shop_average_rating(shop['id'])
                if avg_rating:
                    shop['average_rating'] = avg_rating
                else:
                    shop['average_rating'] = 0.0

                # Hitung jumlah produk
                query_product_count = """
                SELECT COUNT(*) as product_count
                FROM Product
                WHERE shopId = %s
                """
                self.cursor.execute(query_product_count, (shop['id'], ))
                result = self.cursor.fetchone()
                if result:
                    shop['product_count'] = result['product_count']
                else:
                    shop['product_count'] = 0

            return shop
        except Exception as e:
            logger.error(f"Error fetching shop by name: {str(e)}")
            return None

    # === CART METHODS ===

    def get_user_cart(self, user_id: int) -> List[Dict[str, Any]]:
        """
        Mendapatkan isi keranjang belanja pengguna
        """
        try:
            self.reconnect_if_needed()
            # Pertama cek apakah pengguna memiliki cart
            cart_query = """
            SELECT id FROM Cart WHERE userId = %s
            """
            self.cursor.execute(cart_query, (user_id, ))
            cart = self.cursor.fetchone()

            if not cart:
                return []

            # Jika ada cart, ambil item-nya
            query = """
            SELECT ci.id, ci.productId, ci.quantity, ci.createdAt, ci.updatedAt,
                   p.name as product_name, p.price, p.stock, p.photoProduct,
                   s.id as shopId, s.name as shop_name
            FROM CartItem ci
            JOIN Product p ON ci.productId = p.id
            JOIN Shop s ON p.shopId = s.id
            WHERE ci.cartId = %s
            ORDER BY ci.updatedAt DESC
            """
            self.cursor.execute(query, (cart['id'], ))
            cart_items = self.cursor.fetchall()

            # Tambahkan kalkulasi subtotal untuk setiap item
            for item in cart_items:
                item['subtotal'] = item['price'] * item['quantity']

            return cart_items
        except Exception as e:
            logger.error(f"Error fetching user cart: {str(e)}")
            return []

    def get_cart_total(self, user_id: int) -> Dict[str, Any]:
        """
        Mendapatkan total keranjang belanja pengguna
        """
        try:
            self.reconnect_if_needed()
            # Pertama cek apakah pengguna memiliki cart
            cart_query = """
            SELECT id FROM Cart WHERE userId = %s
            """
            self.cursor.execute(cart_query, (user_id, ))
            cart = self.cursor.fetchone()

            if not cart:
                return {
                    'total_amount': 0,
                    'total_items': 0,
                    'total_quantity': 0
                }

            query = """
            SELECT SUM(p.price * ci.quantity) as total_amount,
                   COUNT(ci.id) as total_items,
                   SUM(ci.quantity) as total_quantity
            FROM CartItem ci
            JOIN Product p ON ci.productId = p.id
            WHERE ci.cartId = %s
            """
            self.cursor.execute(query, (cart['id'], ))
            result = self.cursor.fetchone()

            if result and result['total_amount'] is not None:
                return {
                    'total_amount': float(result['total_amount']),
                    'total_items': int(result['total_items']),
                    'total_quantity': int(result['total_quantity'])
                }
            else:
                return {
                    'total_amount': 0,
                    'total_items': 0,
                    'total_quantity': 0
                }
        except Exception as e:
            logger.error(f"Error calculating cart total: {str(e)}")
            return {'total_amount': 0, 'total_items': 0, 'total_quantity': 0}

    def add_to_cart(self,
                    user_id: int,
                    product_id: int,
                    quantity: int = 1) -> bool:
        """
        Menambahkan produk ke keranjang belanja
        """
        try:
            self.reconnect_if_needed()
            # Cek produk tersedia
            product_query = """
            SELECT id, stock FROM Product WHERE id = %s
            """
            self.cursor.execute(product_query, (product_id, ))
            product = self.cursor.fetchone()

            if not product:
                logger.warning(f"Product with ID {product_id} not found")
                return False

            if product['stock'] < quantity:
                logger.warning(
                    f"Insufficient stock for product ID {product_id}")
                return False

            # Cek apakah pengguna memiliki cart
            cart_query = """
            SELECT id FROM Cart WHERE userId = %s
            """
            self.cursor.execute(cart_query, (user_id, ))
            cart = self.cursor.fetchone()

            cart_id = None
            if not cart:
                # Buat cart baru
                create_cart_query = """
                INSERT INTO Cart (userId, createdAt, updatedAt)
                VALUES (%s, NOW(), NOW())
                """
                self.cursor.execute(create_cart_query, (user_id, ))
                cart_id = self.cursor.lastrowid
            else:
                cart_id = cart['id']

            # Cek apakah item sudah ada di cart
            item_query = """
            SELECT id, quantity FROM CartItem 
            WHERE cartId = %s AND productId = %s
            """
            self.cursor.execute(item_query, (cart_id, product_id))
            item = self.cursor.fetchone()

            if item:
                # Update quantity
                new_quantity = item['quantity'] + quantity
                update_query = """
                UPDATE CartItem
                SET quantity = %s, updatedAt = NOW()
                WHERE id = %s
                """
                self.cursor.execute(update_query, (new_quantity, item['id']))
            else:
                # Tambahkan item baru
                insert_query = """
                INSERT INTO CartItem (cartId, productId, quantity, createdAt, updatedAt)
                VALUES (%s, %s, %s, NOW(), NOW())
                """
                self.cursor.execute(insert_query,
                                    (cart_id, product_id, quantity))

            self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Error adding product to cart: {str(e)}")
            self.db.rollback()
            return False

    def update_cart_item(self, cart_item_id: int, quantity: int) -> bool:
        """
        Memperbarui jumlah produk di keranjang belanja
        """
        try:
            self.reconnect_if_needed()
            if quantity <= 0:
                # Hapus item jika quantity 0 atau negatif
                delete_query = """
                DELETE FROM CartItem WHERE id = %s
                """
                self.cursor.execute(delete_query, (cart_item_id, ))
            else:
                # Update quantity
                update_query = """
                UPDATE CartItem
                SET quantity = %s, updatedAt = NOW()
                WHERE id = %s
                """
                self.cursor.execute(update_query, (quantity, cart_item_id))

            self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating cart item: {str(e)}")
            self.db.rollback()
            return False

    def remove_from_cart(self, cart_item_id: int) -> bool:
        """
        Menghapus produk dari keranjang belanja
        """
        try:
            self.reconnect_if_needed()
            delete_query = """
            DELETE FROM CartItem WHERE id = %s
            """
            self.cursor.execute(delete_query, (cart_item_id, ))
            self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Error removing product from cart: {str(e)}")
            self.db.rollback()
            return False

    def clear_cart(self, user_id: int) -> bool:
        """
        Mengosongkan keranjang belanja pengguna
        """
        try:
            self.reconnect_if_needed()
            # Cek apakah pengguna memiliki cart
            cart_query = """
            SELECT id FROM Cart WHERE userId = %s
            """
            self.cursor.execute(cart_query, (user_id, ))
            cart = self.cursor.fetchone()

            if not cart:
                return True  # Tidak ada cart, dianggap sudah kosong

            # Hapus semua item
            delete_query = """
            DELETE FROM CartItem WHERE cartId = %s
            """
            self.cursor.execute(delete_query, (cart['id'], ))
            self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Error clearing user cart: {str(e)}")
            self.db.rollback()
            return False

    # === USER METHODS ===

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Mendapatkan informasi pengguna berdasarkan ID
        """
        try:
            self.reconnect_if_needed()
            query = """
            SELECT id, username, fullName, email, phoneNumber, photoUser, address,
                   createdAt, updatedAt
            FROM User
            WHERE id = %s
            """
            self.cursor.execute(query, (user_id, ))
            user = self.cursor.fetchone()

            if user:
                # Hapus informasi sensitif jika ada
                if 'password' in user:
                    del user['password']

            return user
        except Exception as e:
            logger.error(f"Error fetching user by ID: {str(e)}")
            return None

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Mendapatkan informasi pengguna berdasarkan username
        """
        try:
            self.reconnect_if_needed()
            query = """
            SELECT id, username, fullName, email, phoneNumber, photoUser, address,
                   createdAt, updatedAt
            FROM User
            WHERE username = %s
            """
            self.cursor.execute(query, (username, ))
            user = self.cursor.fetchone()

            if user:
                # Hapus informasi sensitif jika ada
                if 'password' in user:
                    del user['password']

            return user
        except Exception as e:
            logger.error(f"Error fetching user by username: {str(e)}")
            return None

    # === ORDER CREATION METHODS ===

    def create_order_from_cart(self, user_id: int) -> Optional[int]:
        """
        Membuat pesanan baru dari keranjang belanja
        
        Returns:
            Optional[int]: ID pesanan baru jika berhasil, None jika gagal
        """
        try:
            self.reconnect_if_needed()
            # Mulai transaksi
            self.db.start_transaction()

            # Ambil keranjang pengguna
            cart_items = self.get_user_cart(user_id)
            if not cart_items:
                logger.warning(f"Cart is empty for user {user_id}")
                self.db.rollback()
                return None

            # Hitung total
            total_amount = sum(item['price'] * item['quantity']
                               for item in cart_items)

            # Buat order baru
            order_query = """
            INSERT INTO `Order` (userId, totalAmount, status, createdAt, updatedAt)
            VALUES (%s, %s, 'pending', NOW(), NOW())
            """
            self.cursor.execute(order_query, (user_id, total_amount))
            order_id = self.cursor.lastrowid

            # Tambahkan order items
            for item in cart_items:
                item_query = """
                INSERT INTO OrderItem (orderId, productId, quantity, price, createdAt, updatedAt)
                VALUES (%s, %s, %s, %s, NOW(), NOW())
                """
                self.cursor.execute(item_query,
                                    (order_id, item['productId'],
                                     item['quantity'], item['price']))

                # Kurangi stok produk
                update_stock_query = """
                UPDATE Product 
                SET stock = stock - %s 
                WHERE id = %s
                """
                self.cursor.execute(update_stock_query,
                                    (item['quantity'], item['productId']))

            # Bersihkan keranjang
            self.clear_cart(user_id)

            # Commit transaksi
            self.db.commit()
            return order_id
        except Exception as e:
            logger.error(f"Error creating order from cart: {str(e)}")
            self.db.rollback()
            return None

    def create_payment(self,
                       order_id: int,
                       payment_type: str,
                       amount: float,
                       va_number: Optional[str] = None,
                       expiry_time: Optional[datetime] = None) -> bool:
        """
        Membuat pembayaran untuk pesanan
        """
        try:
            self.reconnect_if_needed()
            # Set expiry time default jika tidak ada
            if not expiry_time:
                expiry_time = datetime.now() + timedelta(hours=24)

            query = """
            INSERT INTO Payment (orderId, amount, paymentType, vaNumber, status, statusOrder, 
                                expiryTime, createdAt, updatedAt)
            VALUES (%s, %s, %s, %s, 'pending', 'pending', %s, NOW(), NOW())
            """
            self.cursor.execute(
                query,
                (order_id, amount, payment_type, va_number, expiry_time))
            self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Error creating payment: {str(e)}")
            self.db.rollback()
            return False

    def update_payment_status(self,
                              order_id: int,
                              status: str,
                              status_order: Optional[str] = None) -> bool:
        """
        Memperbarui status pembayaran
        """
        try:
            self.reconnect_if_needed()
            if status_order:
                query = """
                UPDATE Payment
                SET status = %s, statusOrder = %s, updatedAt = NOW()
                WHERE orderId = %s
                """
                self.cursor.execute(query, (status, status_order, order_id))
            else:
                query = """
                UPDATE Payment
                SET status = %s, updatedAt = NOW()
                WHERE orderId = %s
                """
                self.cursor.execute(query, (status, order_id))

            # Jika pembayaran berhasil, update status order
            if status == 'paid':
                order_query = """
                UPDATE `Order`
                SET status = 'paid', updatedAt = NOW()
                WHERE id = %s
                """
                self.cursor.execute(order_query, (order_id, ))

            self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating payment status: {str(e)}")
            self.db.rollback()
            return False

    # === STATS ===

    def get_top_selling_products(self, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Mendapatkan daftar produk terlaris berdasarkan jumlah penjualan
        """
        try:
            self.reconnect_if_needed()
            query = """
            SELECT p.id, p.name, p.photoProduct, p.price, p.stock,
                   SUM(oi.quantity) as total_sold,
                   COUNT(DISTINCT o.id) as order_count
            FROM Product p
            JOIN OrderItem oi ON p.id = oi.productId
            JOIN `Order` o ON oi.orderId = o.id
            WHERE o.status != 'cancelled'
            GROUP BY p.id, p.name, p.photoProduct, p.price, p.stock
            ORDER BY total_sold DESC
            LIMIT %s
            """
            self.cursor.execute(query, (limit, ))
            products = self.cursor.fetchall()
            return products
        except Exception as e:
            logger.error(f"Error fetching top selling products: {str(e)}")
            return []

    def get_sales_summary(self) -> Dict[str, Any]:
        """
        Mendapatkan ringkasan penjualan (total pendapatan, jumlah pesanan, rata-rata pesanan)
        """
        try:
            self.reconnect_if_needed()
            query = """
            SELECT 
                COUNT(id) as total_orders,
                SUM(totalAmount) as total_revenue,
                AVG(totalAmount) as average_order_value
            FROM `Order`
            WHERE status = 'completed'
            """
            self.cursor.execute(query)
            summary = self.cursor.fetchone()

            if not summary or summary['total_orders'] == 0:
                return {
                    'total_orders': 0,
                    'total_revenue': 0,
                    'average_order_value': 0
                }

            # Ambil juga data penjualan hari ini
            today_query = """
            SELECT 
                COUNT(id) as today_orders,
                SUM(totalAmount) as today_revenue
            FROM `Order`
            WHERE status = 'completed' AND DATE(createdAt) = CURDATE()
            """
            self.cursor.execute(today_query)
            today = self.cursor.fetchone()

            if today:
                summary['today_orders'] = today['today_orders'] or 0
                summary['today_revenue'] = today['today_revenue'] or 0
            else:
                summary['today_orders'] = 0
                summary['today_revenue'] = 0

            return summary
        except Exception as e:
            logger.error(f"Error fetching sales summary: {str(e)}")
            return {
                'total_orders': 0,
                'total_revenue': 0,
                'average_order_value': 0,
                'today_orders': 0,
                'today_revenue': 0
            }

    def close(self):
        """
        Menutup koneksi database
        """
        try:
            if hasattr(self, 'cursor') and self.cursor:
                self.cursor.close()
            if hasattr(self, 'db') and self.db:
                self.db.close()
            logger.info("MySQL database connection closed")
        except Exception as e:
            logger.error(f"Error closing MySQL database connection: {str(e)}")
