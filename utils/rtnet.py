import base64
import hashlib
import json

import aiohttp
from ecdsa.keys import VerifyingKey, SigningKey
from fastapi import HTTPException

from db.database import transaction
from endpoint.models import CreatedInvoiceDto


# # VERIFY
# # Вставьте сюда публичный ключ из документации
# public_key_base64 = "MIGbMBAGByqGSM49AgEGBSuBBAAjA4GGAAQBU+2j5U/5R1J9IVuEO1x3yPxeEtBXblH9yjepfGWsfPBcQWqjeRPpxGtFcmqMSZKhFGPcWY5uwc3lLIGiRTrKc4oBqK3UXMU+uiJ2LOt4ukmX/uBZmebBWxhO92hNiDxgpmyUmLr6hKKR/Su6pKaWEXzLrRAkkVPxf/PhpGR+havSR1s="
# # Вставьте сюда тело запроса от нас
# callback_body = """{"EntityType":"Withdrawal","Id":"431","ExternalId":"234345334656","Status":"Sent","Amount":100.00,"InterbankFee":0.00000000000000,"UsdtPrice":0.0}"""
# # Вставьте сюда значение заголовка ECDSA от нас
# signature_hex = "01AF4F05EFB82E87ABD8444EFA7251941D75C2B0B912CE896CB6CB775D76BF26785550247B6C89F5C7DB350F0A2A5AE9F896B2A7F956E3047DA8B14AA10F8E206EB601FC90CD0C0A3E79A7F117EBD7425D121B4531D829DD7247E6BAE17032B299A7BCB155F0110376FF69976B23BDC67C006944C679EAF83F8C16EE0C0B4E851B028738"
#
# verifying_key = VerifyingKey.from_der(base64.b64decode(public_key_base64))
# normalized_callback_body = str.encode(callback_body.lower())
# signature_bytes = bytes.fromhex(signature_hex)
# verify_result = verifying_key.verify(signature_bytes, normalized_callback_body, hashfunc=hashlib.sha512)
# print("Signature valid: " + str(verify_result))
#
#
# # SIGN
# from ecdsa.keys import SigningKey
# import base64
# import hashlib
# import requests
#
# # Вставьте сюда необходимый API URL
# api_url = "https://rt-demo.netex24.net/api/merchant/Balance/GetBalance"
# # Вставьте сюда тело вашего запроса
# request_body = ""
#
# private_key = SigningKey.from_der(base64.b64decode(private_key_base64))
# signing_data = str.encode((request_body + api_id).lower())
# signature = private_key.sign(signing_data, hashfunc=hashlib.sha512)
# signature_hex = signature.hex()
# auth_header_value = signature_hex + ":" + api_id
#
# response = requests.get(api_url, headers={"ECDSA":auth_header_value})
# print("API Response: " + response.text)

class RtnetAPI:
    PUBLIC_KEY = "MIGbMBAGByqGSM49AgEGBSuBBAAjA4GGAAQBU+2j5U/5R1J9IVuEO1x3yPxeEtBXblH9yjepfGWsfPBcQWqjeRPpxGtFcmqMSZKhFGPcWY5uwc3lLIGiRTrKc4oBqK3UXMU+uiJ2LOt4ukmX/uBZmebBWxhO92hNiDxgpmyUmLr6hKKR/Su6pKaWEXzLrRAkkVPxf/PhpGR+havSR1s="

    def __init__(
            self,
            project_id: str,
            api_id: str,
            private_key_base64: str,
            base_url: str,
    ):
        self.project_id = project_id
        self.api_id = api_id
        self.private_key = SigningKey.from_der(base64.b64decode(private_key_base64))
        self.session = aiohttp.ClientSession(base_url=base_url)

    @staticmethod
    def validate(request_body: str, sign: str) -> bool:
        verifying_key = VerifyingKey.from_der(base64.b64decode(RtnetAPI.PUBLIC_KEY))
        normalized_callback_body = str.encode(request_body.lower())
        signature_bytes = bytes.fromhex(sign)
        verify_result = verifying_key.verify(signature_bytes, normalized_callback_body, hashfunc=hashlib.sha512)
        print("Signature valid: " + str(verify_result))
        return verify_result

    def sign(self, request_body: str) -> str:
        signing_data = str.encode((request_body + self.api_id).lower())
        signature = self.private_key.sign(signing_data, hashfunc=hashlib.sha512)
        signature_hex = signature.hex()
        auth_header_value = signature_hex + ":" + self.api_id

        return auth_header_value

    @staticmethod
    def headers(sign) -> dict[str, str]:
        return {
            "ECDSA": sign,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def create_withdrawal(
            self,
            client_id: int,
            external_id: str,
            payment_method: str,
            amount: int,
            client_card_number: str,
            ext_ip: str,
    ):
        body = {
            "clientId": client_id,
            "externalId": external_id,
            "paymentMethod": payment_method,
            "amount": amount,
            "clientCardNumber": client_card_number,
            "extIP": ext_ip,
            "projectId": self.project_id,
        }
        sign = self.sign(json.dumps(body))
        async with self.session.post(
                "/api/merchant/Withdrawal/Create",
                json=body,
                headers=self.headers(sign),
                ssl=False,
        ) as r:
            if r.status != 200:
                raise HTTPException(detail=f"failed to create withdrawal {await r.text()}", status_code=400)
            print(await r.json())

    @transaction()
    async def create_deposit(
            self,
            client_id: int,
            external_id: str,
            payment_method: str,
            amount: int,
    ) -> CreatedInvoiceDto:
        body = {
            "clientId": client_id,
            "externalId": external_id,
            "paymentMethod": payment_method,
            "amount": amount,
            "projectId": self.project_id,
        }
        sign = self.sign(json.dumps(body))
        async with self.session.post(
                "/api/merchant/Invoice/Create",
                json=body,
                headers=self.headers(sign),
                ssl=False,
        ) as r:
            if r.status != 200:
                raise HTTPException(detail=f"failed to create deposit {await r.text()}", status_code=400)
            response = CreatedInvoiceDto.model_validate(await r.json())
        return response
