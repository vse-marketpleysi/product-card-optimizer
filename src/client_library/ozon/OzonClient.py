import requests
import uuid
from datetime import datetime, timedelta

from ..client_exception import ClientException

class OzonClient:
    api_key: str
    client_id: str
    base_url: str

    def __init__(self, client_id, api_key):
        self.api_key = api_key
        self.client_id = client_id
        self.base_url = "https://api-seller.ozon.ru"
        

    def request(self, method: str, endpoint: str, body={}):
        url = self.base_url + endpoint
        headers = {'Client-Id': self.client_id, 'Api-Key': self.api_key}
        response = requests.request(method, url, headers=headers, json=body)
        return self.parse_request_response(response, endpoint, body)
    
    def parse_request_response(self, response, endpoint, body):
        status_code = response.status_code
        try:
            data = response.json()
        except ValueError:
            data = []

        if 200 <= status_code < 300:
            pass
        elif 400 <= status_code < 500:
            # Client Error
            raise ClientException(f'Client error occurred. Status code: {status_code}, Endpoint: {endpoint}, Response: {response.text}, Data: {body}', data)
        elif 500 <= status_code < 600:
            # Server Error
            raise ClientException(f'Server error occurred. Status code: {status_code}, Endpoint: {endpoint}, Response: {response.text}, Data: {body}', data)
        else:
            raise ClientException(f'Unexpected status code: {status_code}, Endpoint: {endpoint}, Response: {response.text}, Data: {body}', data)

        if "package-label" in endpoint:
            filename = "db/tmp/" + f'ozon_{str(uuid.uuid4())}.pdf'
            with open(filename, 'wb') as f:
                f.write(response.content)
            return filename
        elif "get-barcode" in endpoint:
            filename = "db/tmp/" + f'ozon_{str(uuid.uuid4())}.png'
            with open(filename, 'wb') as f:
                f.write(response.content)
            return filename
        else:
            if response.text:
                return response.json()
            else:
                return None

    def get_products(self, body):
        return self.request("POST", "/v2/product/list", body)
    
    def get_products_info(self, body):
        return self.request("POST", "/v2/product/info", body)

    def get_products_description(self, body):
        return self.request("POST", "v1/product/info/description", body)

    def get_fbs_postings(self, body):
        return self.request("POST", "/v3/posting/fbs/list", body)
    
    def get_fbo_postings(self, body):
        return self.request("POST", "/v2/posting/fbo/list", body)
    
    def get_fbs_returns(self, body):
        return self.request("POST", "/v3/returns/company/fbs", body)
    
    # You can't pass more than 20 posting numbers at once
    def get_lables(self, posting_numbers):
        body = {
            "posting_number": posting_numbers
        }
        return self.request("POST", "/v2/posting/fbs/package-label", body)
    
    def get_all_fbs_postings(self, days: int):
        to = datetime.now()
        since = to - timedelta(days=days)
        to_string = to.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        since_string = since.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        postings_body = {
            "dir": "ASC",
            "filter": {
                "since": since_string,
                "to": to_string
            },
            "limit": 1000,
            "offset": 0,
            "translit": True,
            "with": {
                "financial_data": True,
                "analytics_data": True
            }
        }
        all_fbs_postings = []
        while True:
            fbs_postings = self.get_fbs_postings(postings_body)
            all_fbs_postings.extend(fbs_postings["result"]["postings"])
            if not fbs_postings["result"]["has_next"]:
                break
            postings_body["offset"] += 1000
        return all_fbs_postings
    
    def get_all_products(self, is_archived = False):
        products_body = {
            "last_id": "",
            "limit": 1000
        }

        if is_archived:
            products_body["filter"] = {"visibility": "ARCHIVED"}

        all_products = []
        total = 0
        while True:
            products = self.get_products(products_body)
            all_products.extend(products["result"]["items"])
            total += products_body["limit"]
            if products["result"]["total"] <= total:
                break
            products_body["last_id"] = products["result"]["last_id"]
        
        all_offer_ids = [product["offer_id"] for product in all_products]
        
        n = 1000 # max size
        all_offer_ids_splitted = [all_offer_ids[i * n:(i + 1) * n] for i in range((len(all_offer_ids) + n - 1) // n )]

        all_products = []
        for offer_ids in all_offer_ids_splitted:
            body = {
                "offer_id": offer_ids,
                "product_id": [],
                "sku": []
            }
            response = self.get_products_info(body)
            all_products.extend(response["result"]["items"])

        return all_products
    
    def ship_order(self, posting_number, packages):
        body = {
            'posting_number': posting_number,
            'packages': packages
        }
        return self.request("POST", "/v3/posting/fbs/ship", body)

    def send_products(self, products):
        body = {
            'items': products
        }
        return self.request("POST", "/v2/product/import", body)

    def get_attribute_values(self, category_id, attribute_id):
        body = {
            "attribute_id": attribute_id,
            "category_id": int(category_id),
            "language": "DEFAULT",
            "last_value_id": 0,
            "limit": 5000
        }
        return self.request("POST", "/v2/category/attribute/values", body)
        
    def get_attributes(self, category_id):
        body = {
            "attribute_type": "ALL",
            "category_id": [
                int(category_id)
            ],
            "language": "DEFAULT"
        }
        return self.request("POST", "/v3/category/attribute", body)

    def send_inventory(self, stocks):
        body = {
            "stocks": stocks
        }
        return self.request("POST", "/v2/products/stocks", body)

    def create_act(self, delivery_method_id: str, departure_date: str):
        body = {
            "delivery_method_id": delivery_method_id,
            "departure_date": departure_date
        }

        return self.request("POST", "/v2/posting/fbs/act/create", body)
    
    def get_barcode(self, id: str):
        body = {
            "id": id
        }

        return self.request("POST", "/v2/posting/fbs/act/get-barcode", body)
    
    def get_transactions(self, since: str, to: str):
        body = {
            "date": {
                "from": since,
                "to": to
            },
            "transaction_type": "all"
        }

        return self.request("POST", "/v3/finance/transaction/totals", body)
    
    def archive_products(self, product_ids):
        body = {
            "product_id": product_ids
        }

        return self.request("POST", "/v1/product/archive", body)
    
    def delete_products(self, offer_ids):
        body = {
            "products": [{"offer_id": str(id)} for id in offer_ids]
        }

        return self.request("POST", "/v2/products/delete", body)
    
    def send_price(self, prices):
        body = {
            "prices": prices
        }

        return self.request("POST", "/v1/product/import/prices", body)

    def update_product_attributes(self, offer_id, attributes):
        body = {
            'items': [
                {
                    'offer_id': offer_id,
                    'attributes': attributes
                }
            ]
        }
        # print('body', body)

        return self.request("POST", "/v1/product/attributes/update", body)
    
    def get_product_attributes(self, offer_id):
        body = {
            'filter': {
                'offer_id': [offer_id],
                "visibility": "ALL"
            },
            'limit': 1
        }
        return self.request("POST", "/v3/products/info/attributes", body)