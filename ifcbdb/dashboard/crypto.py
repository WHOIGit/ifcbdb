import base64
import hashlib

from Crypto import Random
from Crypto.Cipher import AES

class AESCipher(object):
    """encryption/decryption utility that supports Unicode keys and plaintexts"""

    @staticmethod
    def _b64_encode(string):
        # return string as base64 encoded utf-8 data
        return base64.b64encode(string.encode('utf-8')).decode('ascii')

    @staticmethod
    def _b64_decode(string):
        # decode the results of _b64_encode
        return base64.b64decode(string).decode('utf-8')
    
    def __init__(self, key):
        # use a safe key, you can use generate_key to give you one.
        # hash the key to 1) make it the right length, 2) support Unicode
        self.key = hashlib.sha256(key.encode()).digest()

    def encrypt(self, raw):
        if len(raw) == 0:
            raise ValueError('zero-length plaintext not allowed')
        encoded_text = self._b64_encode(raw)
        raw = self._pad(encoded_text)
        iv = Random.new().read(AES.block_size)
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        return base64.b64encode(iv + cipher.encrypt(raw)).decode('ascii')

    def decrypt(self, enc):
        enc = base64.b64decode(enc)
        iv = enc[:AES.block_size]
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        # there are two failure modes if the wrong key is used:
        # 1. a zero-length string due to failure to decode base64
        # 2. non-ASCII bytes trying to treat garbage plaintext as base64
        try:
            plaintext = self._b64_decode(self._unpad(cipher.decrypt(enc[AES.block_size:])).decode('ascii'))
        except UnicodeDecodeError:
            # case 2
            raise ValueError('wrong encryption key, cannot decrypt')
        # case 1
        if len(plaintext) == 0:
            raise ValueError('wrong encryption key, cannot decrypt')
        return plaintext

    @staticmethod
    def _pad(s):
        bs = AES.block_size
        return s + (bs - len(s) % bs) * chr(bs - len(s) % bs)

    @staticmethod
    def _unpad(s):
        return s[:-ord(s[len(s)-1:])]

    @staticmethod
    def generate_key(size=64):
        random_bytes = Random.new().read(size)
        key = base64.b64encode(random_bytes).decode('ascii')
        return key
