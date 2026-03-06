import bcrypt
import jwt
import base64
import os
from cryptography.fernet import Fernet
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, current_app
import logging

logger = logging.getLogger(__name__)


class DataEncryption:
    def __init__(self, key=None):
        if key is None:
            self.key = self.generate_key()
        else:
            self.key = key
        self.cipher = Fernet(self.key)

    def generate_key(self):
        """Генерация ключа для шифрования"""
        return Fernet.generate_key()

    def encrypt_data(self, data):
        """Шифрование данных"""
        try:
            if isinstance(data, str):
                data = data.encode()
            elif isinstance(data, dict):
                data = str(data).encode()
            return self.cipher.encrypt(data)
        except Exception as e:
            logger.error(f"Encryption error: {e}")
            return None

    def decrypt_data(self, encrypted_data):
        """Дешифрование данных"""
        try:
            decrypted = self.cipher.decrypt(encrypted_data)
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Decryption error: {e}")
            return None


class Authentication:
    @staticmethod
    def hash_password(password):
        """Хеширование пароля"""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt)

    @staticmethod
    def verify_password(password, hashed):
        """Проверка пароля"""
        return bcrypt.checkpw(password.encode('utf-8'), hashed)

    @staticmethod
    def generate_token(user_id, username, secret_key, expires_in=24):
        """Генерация JWT токена"""
        payload = {
            'user_id': user_id,
            'username': username,
            'exp': datetime.utcnow() + timedelta(hours=expires_in)
        }
        return jwt.encode(payload, secret_key, algorithm='HS256')

    @staticmethod
    def verify_token(token, secret_key):
        """Проверка JWT токена"""
        try:
            payload = jwt.decode(token, secret_key, algorithms=['HS256'])
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None


class BackupManager:
    def __init__(self, backup_path):
        self.backup_path = backup_path
        self.encryption = DataEncryption()

        # Создаем папку для бэкапов если её нет
        os.makedirs(backup_path, exist_ok=True)

    def create_backup(self, data_type, data):
        """Создание резервной копии"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"{self.backup_path}/{data_type}_backup_{timestamp}.enc"

        try:
            # Шифрование данных перед сохранением
            if isinstance(data, list) or isinstance(data, dict):
                import json
                data_str = json.dumps(data, default=str)
            else:
                data_str = str(data)

            encrypted_data = self.encryption.encrypt_data(data_str)

            with open(backup_file, 'wb') as f:
                f.write(encrypted_data)

            logger.info(f"Backup created: {backup_file}")
            return backup_file
        except Exception as e:
            logger.error(f"Backup creation failed: {e}")
            return None

    def restore_backup(self, backup_file):
        """Восстановление из резервной копии"""
        try:
            with open(backup_file, 'rb') as f:
                encrypted_data = f.read()

            decrypted_data = self.encryption.decrypt_data(encrypted_data)

            # Пытаемся распарсить JSON
            try:
                import json
                return json.loads(decrypted_data)
            except:
                return decrypted_data

        except Exception as e:
            logger.error(f"Backup restoration failed: {e}")
            return None


def token_required(f):
    """Декоратор для проверки JWT токена"""

    @wraps(f)
    def decorated(*args, **kwargs):
        token = None

        # Ищем токен в заголовке
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            parts = auth_header.split()
            if len(parts) == 2 and parts[0].lower() == 'bearer':
                token = parts[1]

        if not token:
            return jsonify({'message': 'Token is missing!'}), 401

        try:
            payload = Authentication.verify_token(token, current_app.config['SECRET_KEY'])
            if payload is None:
                return jsonify({'message': 'Token is invalid or expired!'}), 401

            # Добавляем данные пользователя в запрос
            request.user = payload
        except Exception as e:
            return jsonify({'message': 'Token verification failed!'}), 401

        return f(*args, **kwargs)

    return decorated